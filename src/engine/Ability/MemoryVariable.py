from engine.MtGObject import MtGObject
from engine.Match import isPlayer
from engine.GameEvent import *

__all__ = ["timestep_damage_tracker", "damage_tracker",
           "graveyard_tracker", "spell_record",
           "combat_tracker", "cards_tracker", "life_tracker"]

class MemoryVariable(MtGObject):
    def __init__(self):
        self.register(self.reset, event=TurnFinishedEvent())
    def value(self): raise NotImplementedError()
    def reset(self): pass
    def __int__(self):
        return int(self.value())
    def __long__(self):
        return long(self.value())
    #def __str__(self):
    #    return str(self.value())

# XXX Do I still need this?
class ZoneMoveVariable(MemoryVariable):
    def __init__(self, from_zone, to_zone):
        self.from_zone = from_zone
        self.to_zone = to_zone
        self.moved = {}
        self.register(self.filter, CardEnteringZoneFrom())
        super(ZoneMoveVariable, self).__init__()
    def reset(self):
        self.moved = {}
    def filter(self, sender, from_zone, oldcard, newcard):
        if str(sender) == self.to_zone and str(from_zone) == self.from_zone:
            # Keep track of the new object - we know where it came from
            # Should I track the object it used to be in case of rollback?
            self.moved[oldcard] = newcard
    def __len__(self): return len(self.moved)
    def value(self): return len(self)
    def __contains__(self, card): return card in self.moved
    def get(self, match=lambda c: True):
        return [card for card in self.moved if match(card)]
    def __iter__(self): return iter(self.get())
    def get_linked(self, card):
        return self.moved.get(card, None)

class DamageTrackingVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.damage, event=DealsDamageToEvent())
        super(DamageTrackingVariable, self).__init__()
    def reset(self):
        self.dealing = {}
    def value(self): return 0
    def damage(self, sender, to, amount):
        if not sender in self.dealing: self.dealing[sender] = {}
        if not to in self.dealing[sender]: self.dealing[sender][to] = 0
        self.dealing[sender][to] += amount
    def dealt(self, source, to=None):
        return source in self.dealing and (to == None or to in self.dealing[source])
    def received(self, to, source=None):
        if source: return self.dealt(source, to)
        else: return any([True for dealing in self.dealing.values() if to in dealing])
    def dealt_by(self, source):
        return self.dealing.get(source, {}).keys()
    def received_by(self, to):
        return [source for source, dealing in self.dealing.items() if to in dealing]
    def amount_dealt(self, source, to=None):
        if not source in self.dealing: return 0
        elif to == None: return sum(self.dealing[source].values())
        else: return self.dealing[source][to]
    def amount_received(self, to, source=None):
        if source: return self.amount_dealt(source, to)
        else: return sum([dealing[to] for dealing in self.dealing.values() if to in dealing])

# To see how many cards a given player has drawn this turn (used by e.g. Archmage Ascension).
class CardDrawingTrackingVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.draw, event=DrawCardEvent())
        super(CardDrawingTrackingVariable, self).__init__()
    def reset(self):
        self.drawn = {}
    def value(self): return sum(self.drawn.values()) # Total cards drawn this turn
    def draw(self, sender):
        if not sender in self.drawn: self.drawn[sender] = 1
        else: self.drawn[sender] += 1
    def player_check(self, player):
        if not player in self.drawn: return 0
        else: return self.drawn[player]

# Complements DamageTrackingVariable. Used by a *lot* of cards, just never added until now (Those purely in trigger conditions: Luminarch Ascension, Needlebite Trap, Bloodchief Ascension, and Sygg, River Cutthroat).
class LifeChangeTrackingVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.lose, event=LifeLostEvent())
        self.register(self.gain, event=LifeGainedEvent())
        super(LifeChangeTrackingVariable, self).__init__()
    def reset(self):
        self.lost = {}
        self.gained = {}
    def value(self): raise NotImplementedError # What exactly would this return?
    def lose(self, sender, amount):
        if not sender in self.lost: self.lost[sender] = amount
        else: self.lost[sender] += amount
    def gain(self, sender, amount):
        if not sender in self.gained: self.gained[sender] = amount
        else: self.gained[sender] += amount
    def amount_lost(self, player):
        if not player in self.lost: return 0
        else: return self.lost[player]
    def amount_gained(self, player):
        if not player in self.gained: return 0
        else: return self.gained[player]

class PlaySpellVariable(MemoryVariable):
    def __init__(self, condition):
        self.was_played = False
        self.condition = condition
        self.register(self.played, event=SpellPlayedEvent())
        super(PlaySpellVariable, self).__init__()
    def played(self, sender, spell):
        if self.condition(spell):
            self.was_played = True
    def value(self): return self.was_played
    def reset(self): self.was_played = False

class SpellRecordVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.played, event=SpellPlayedEvent())
        super(SpellRecordVariable, self).__init__()
    def reset(self):
        self.record = {}
    def played(self, sender, spell):
        if not sender in self.record: self.record[sender] = set()
        self.record[sender].add(spell)
    def value(self): return sum([len(self.record[player]) for player in self.record])
    def get(self, condition=lambda s: True, player=None):
        if player and player in self.record: return [spell for spell in self.record[player] if condition(spell)]
        elif not player:
            temp = []
            for player in self.record: temp.extend([spell for spell in self.record[player] if condition(spell)])
            return temp
        else: return []

# Now serves two purposes: Purpose one, looking back over the entire turn (for cards like Norritt) to see who attacked/blocked (and whether or not they blocked a certain card).
# Purpose two is looking back at the previous combat step, which I discovered is needed for a couple cards whose combat states are cleared before they can refer to them (Greater Werewolf). I'm sure it will have other uses as well, but I don't really have the time to go fishing for every card that needs to refer to combat information, so I'll just leave it be and as we find uses for it, we'll use it. -MageKing17
class CombatTrackingVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.attacker, event=AttackerDeclaredEvent())
        self.register(self.blocker, event=BlockerDeclaredEvent())
        self.register(self.clear_local, event=TurnFinishedEvent())
        super(CombatTrackingVariable, self).__init__()
    def reset(self):
        self.attackers = {}
        self.blockers = {}
        self.attacked = {}
        self.blocked = {}
    def attacker(self, sender):
        self.attackers[sender] = []
        self.attacked[sender] = []
    def blocker(self, sender, attacker):
        self.blockers[sender] = [attacker]
        if not sender in self.blocked: self.blocked[sender] = [attacker]
        else: self.blocked[sender].append(attacker)
        self.attackers[attacker].append(sender)
        self.attacked[attacker].append(sender)
    def clear_local(self):
        self.attackers = {}
        self.blockers = {}
    def value(self): return 0
    def get_blocked_by(self, blocker, entire_turn=True):
        if entire_turn and blocker in self.blocked: return self.blocked[blocker]
        elif blocker in self.blockers: return self.blockers[blocker]
        else: return []
    def get_attacked(self, attacker, entire_turn=True):
        if entire_turn: return attacker in self.attacked
        else: return attacker in self.attacker
    def get_blocked_attacker(self, attacker, entire_turn=True):
        if entire_turn and attacker in self.attacked: return self.attacked[attacker]
        elif attacker in self.attackers: return self.attackers[attacker]
        else: return []

# This should never be referred to... it's solely to make damage triggers work properly
class TimestepDamageTrackingVariable(MemoryVariable):
    def __init__(self):
        self.reset()
        self.register(self.damage, event=DealsDamageToEvent())
        self.register(self.cleanup, event=TimestepEvent())
    def reset(self):
        self.dealing = {}
        self.receiving = {}
    def cleanup(self):
        for source in self.dealing:
            if self.dealing[source]['combat'] > 0:
                source.send(DealsDamageEvent(), amount=self.dealing[source]['combat'], combat=True)
            if self.dealing[source]['other'] > 0:
                source.send(DealsDamageEvent(), amount=self.dealing[source]['other'], combat=False)
        for recipient in self.receiving:
            if self.receiving[recipient]['combat'] > 0: recipient.send(ReceivesDamageEvent(), amount=self.receiving[recipient]['combat'], combat=True)
            if self.receiving[recipient]['other'] > 0: recipient.send(ReceivesDamageEvent(), amount=self.receiving[recipient]['other'], combat=False)
        self.reset()
    def damage(self, sender, to, amount, combat):
        if not sender in self.dealing: self.dealing[sender] = {'combat': 0, 'other': 0}
        if not to in self.receiving: self.receiving[to] = {'combat': 0, 'other': 0}
        if combat:
            self.dealing[sender]['combat'] += amount
            self.receiving[to]['combat'] += amount
        else:
            self.dealing[sender]['other'] += amount
            self.receiving[to]['other'] += amount
    def value(self):
        return sum([self.tracking[source]['combat'] + self.tracking[source]['other'] for source in self.tracking])

timestep_damage_tracker = TimestepDamageTrackingVariable()

# Predefined memory variables
damage_tracker = DamageTrackingVariable()
graveyard_tracker = ZoneMoveVariable(from_zone="battlefield", to_zone="graveyard")
spell_record = SpellRecordVariable()
combat_tracker = CombatTrackingVariable()
cards_tracker = CardDrawingTrackingVariable()
life_tracker = LifeChangeTrackingVariable()
