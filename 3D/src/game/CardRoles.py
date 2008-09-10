import new, copy, itertools
from characteristics import stacked_controller, PTModifiers
from GameObjects import MtGObject
from GameEvent import DealsDamageEvent, DealsDamageToEvent, ReceivesDamageEvent, CardTapped, CardUntapped, PermanentDestroyedEvent, AttachedEvent, UnAttachedEvent, AttackerDeclaredEvent, AttackerBlockedEvent, BlockerDeclaredEvent, TokenLeavingPlay, TargetedByEvent, PowerToughnessChangedEvent, NewTurnEvent, TimestepEvent, CounterAddedEvent, CounterRemovedEvent, AttackerClearedEvent, BlockerClearedEvent, CreatureInCombatEvent, CreatureCombatClearedEvent
from Ability.Counters import Counter, PowerToughnessCounter

class GameRole(MtGObject):
    def info():
        def fget(self): 
            txt = [str(self.name)]
            color = str(self.color)
            if color: txt.append("\n%s"%color)
            txt.append("\n") 
            supertype = str(self.supertype)
            if supertype: txt.append(supertype+" ")
            cardtype = str(self.type)
            if cardtype: txt.append(cardtype)
            subtypes = str(self.subtypes)
            if subtypes: txt.append(" - %s"%subtypes)
            abilities = str(self.abilities)
            if abilities: txt.append('\n\n%s'%abilities)
            if self.counters: txt.append('\n\nCounters: %s'%', '.join(map(str,self.counters)))
            #subrole_info = self.subrole_info()
            #if subrole_info: txt.append('\n\n'+subrole_info)
            return ''.join(txt)
        return locals()
    info = property(**info())
    controller = property(fget=lambda self: self.owner)
    power = property(fget=lambda self: self.base_power)
    toughness = property(fget=lambda self: self.base_toughness)

    def __init__(self, card):
        self.card = card
        self._counters = []
        self.attachments = []
        self.is_LKI = False
    def send(self, *args, **named):
        self.card.send(*args, **named)
    def dealDamage(self, to, amount, combat=False):
        final_dmg = 0
        if to.canBeDamagedBy(self.card) and amount > 0:
            final_dmg = to.assignDamage(amount, source=self.card, combat=combat)
            if final_dmg > 0: self.send(DealsDamageToEvent(), to=to, amount=final_dmg, combat=combat)
        #self.send(DealsDamageEvent(), amount=final_dmg, combat=combat)
        return final_dmg
    def canBeTargetedBy(self, targeter): return True
    def canBeAttachedBy(self, targeter): return True
    def isTargetedBy(self, targeter):
        self.send(TargetedByEvent(), targeter=targeter)
    def enteringZone(self, zone):
        self.abilities.enteringZone(zone)
    def leavingZone(self, zone):
        self.abilities.leavingZone(zone)
        for attached in self.attachments: attached.attachedLeavingPlay()
    def move_to(self, zone, position="top"):
        self.card.move_to(zone, position)
    def add_counters(self, counter_type, number=1):
        if type(counter_type) == str: counter_type = Counter(counter_type)
        for counter in [counter_type.copy() for i in range(number)]:
            self._counters.append(counter)
            self.send(CounterAddedEvent(), counter=counter)
    def remove_counters(self, counter_type, number=1):
        num = 0
        for counter in itertools.islice((c for c in self._counters if c == counter_type), number):
            num += 1
            self._counters.remove(counter)
            self.send(CounterRemovedEvent(), counter=counter)
        return num  # Return the number of counters we actually removed
    def num_counters(self, counter=None):
        if counter: return len([c for c in self._counters if c == counter])
        else: return len(self._counters)
    counters = property(fget=lambda self: self._counters)
    def __deepcopy__(self,memo,mutable=set([list,set,dict])):
        newcopy = copy.copy(self)
        for attr, value in self.__dict__.iteritems():
            if type(value) in mutable: setattr(newcopy,attr,copy.copy(value))
            else: setattr(newcopy,attr, value)
        return newcopy
    def __str__(self):
        return self.__class__.__name__

# For token objects out of play
class NoRole(GameRole): pass

# Cards out of play
class CardRole(GameRole): pass

# Cards on the stack
class SpellRole(GameRole):
    def __init__(self, card):
        super(SpellRole, self).__init__(card)
        self.facedown = False
    def faceDown(self):
        self.facedown = True
    def faceUp(self):
        self.facedown = False

class Permanent(GameRole):
    controller = property(fget=lambda self: self._controller.get())
    continuously_in_play = property(fget=lambda self: self._continuously_in_play)
    def initialize_controller(self, controller):
        self._controller = stacked_controller(self, controller)
    def change_controller(self, new_controller):
        return self._controller.set(new_controller)
    def __init__(self, card):
        super(Permanent, self).__init__(card)
        self._controller = None
        self.tapped = False
        self.flipped = False
        self.facedown = False
        self._continuously_in_play = False
    def faceDown(self):
        self.facedown = True
    def faceUp(self):
        self.facedown = False
    def canBeTapped(self): # Called by game action (such as an effect)
        return not self.tapped
    def canTap(self): # Called as a result of user action
        return not self.tapped
    def tap(self):
        # Don't tap if already tapped:
        if self.canBeTapped():
            self.tapped = True
            self.send(CardTapped())
            return True
        else: return False
    def canUntap(self):
        return self.tapped
    def untap(self):
        if self.tapped:
            self.tapped = False
            self.send(CardUntapped())
            return True
        else: return False
    def shouldDestroy(self):
        # This is called to check whether the permanent should be destroyed (by SBE)
        return True
    def canDestroy(self):
        # this can be replaced by regeneration for creatures - what about artifacts and enchantments?
        return True
    def destroy(self, regenerate=True):
        if not regenerate or self.canDestroy():
            self.move_to(self.owner.graveyard)
            self.send(PermanentDestroyedEvent())
    def continuouslyInPlay(self):
        return self.continuously_in_play
    def summoningSickness(self):
        def remove_summoning_sickness(player):
            if self.controller == player:
                self.unregister(remove_summoning_sickness, NewTurnEvent(), weak=False)
                self._continuously_in_play = True
        self._continuously_in_play = False
        self.register(remove_summoning_sickness, NewTurnEvent(), weak=False)

    def enteringZone(self, zone):
        # Add the necessary superclasses, depending on our type/subtypes
        self.__class__ = new.classobj("_Permanent", (Permanent,), {})
        self.add_basecls()
        super(Permanent, self).enteringZone(zone)
    def leavingZone(self, zone):
        # Add the necessary superclasses, depending on our type/subtypes
        # Don't remove the superclasses, because of LKI
        self.deactivateRole()
        super(Permanent, self).leavingZone(zone)
    def activateRole(self): pass
    def deactivateRole(self): pass
    def add_basecls(self):
        cls = self.__class__
        orig_bases = cls.__bases__
        if self.type == "Creature" and not Creature in orig_bases:
            cls.__bases__ = (Creature,)+orig_bases
            self.activateCreature()
        if (self.subtypes == "Aura" or self.subtypes == "Equipment") and not Attachment in orig_bases:
            cls.__bases__ = (Attachment,)+orig_bases
            self.activateAttachment()
    #def add_basecls(self):
    #    base_classes = set()
    #    if self.type == "Creature": base_classes.append(Creature)
    #    if self.subtypes == "Aura" or self.subtypes == "Equipment": base_classes.append(Attachment)
    #    if base_classes:
    #        self.__class__ = new.classobj("_Permanent", tuple(base_classes)+(Permanent,), {})
    #        self.activateRole()

class Creature(object):
    def power():
        def fget(self):
            if self.cached_PT_dirty: self._calculate_power_toughness()
            return self.curr_power
        def fset(self, power):
            self.base_power.cda(power)
        return locals()
    power = property(**power())
    def toughness():
        def fget(self):
            if self.cached_PT_dirty: self._calculate_power_toughness()
            return self.curr_toughness
        def fset(self, toughness):
            self.base_toughness.cda(toughness)
        return locals()
    toughness = property(**toughness())
    def _calculate_power_toughness(self):
        # Calculate layering rules
        power, toughness = int(self.base_power), int(self.base_toughness) # layer 6a
        power, toughness = self.PT_other_modifiers.calculate(power, toughness) # layer 6b
        power += sum([c.power for c in self.counters if hasattr(c,"power")]) # layer 6c
        toughness += sum([c.toughness for c in self.counters if hasattr(c,"toughness")]) # layer 6c
        power, toughness = self.PT_static_modifiers.calculate(power, toughness) # layer 6d
        power, toughness = self.PT_switch_modifiers.calculate(power, toughness) # layer 6e
        self.cached_PT_dirty = False
        self.curr_power, self.curr_toughness = power, toughness
    def _PT_changed(self, sender): self.cached_PT_dirty=True
    def activateCreature(self):
        self.curr_power = self.curr_toughness = 0
        self.cached_PT_dirty = False

        # Only accessed internally
        self.__damage = 0

        self.PT_other_modifiers = PTModifiers() # layer 6b - other modifiers
        self.PT_static_modifiers = PTModifiers() # layer 6d - static modifiers
        self.PT_switch_modifiers = PTModifiers() # layer 6e - P/T switching modifiers
        self.in_combat = False
        self.attacking = False
        self.blocking = False
        self.blocked = False
        self.cached_PT_dirty = True

        self.register(self._PT_changed, TimestepEvent())
        #super(Creature,self).activateRole()
    def deactivateRole(self):
        self.unregister(self._PT_changed, TimestepEvent())
        super(Creature,self).deactivateRole()
    def canBeDamagedBy(self, damager):
        return not self.is_LKI
    def combatDamage(self):
        return self.power
    def clearDamage(self):
        self.__damage = 0
    def currentDamage(self):
        return self.__damage
    def assignDamage(self, amt, source, combat=False):
        if amt > 0:
            if "wither" in source.abilities: self.add_counters(PowerToughnessCounter(-1, -1), amt)
            else: self.__damage += amt
            self.send(ReceivesDamageEvent(), source=source, amount=amt, combat=combat)
        return amt
    def trample(self, damage_assn):
        from Match import isCreature
        total_damage = self.combatDamage()
        total_applied = 0
        not_enough = False
        for b in damage_assn.keys():
            # Skip players and blockers who no longer exist
            if not isCreature(b): continue
            # if total assigned damage is lethal
            # lethal_damage will never be less than 1
            lethal_damage = b.toughness-b.currentDamage()
            assert lethal_damage >= 1, "Error in damage calculation"
            if damage_assn[b] < lethal_damage:
                not_enough = True
                break
            total_applied += damage_assn[b]
        if not_enough: return 0
        else: return total_damage - total_applied
    def checkAttack(self, attackers, not_attacking):
        return True
    def canAttack(self):
        return (not self.tapped) and (not self.in_combat) and self.continuouslyInPlay()
    def checkBlock(self, combat_assignment, not_blocking):
        return True
    def canBeBlocked(self):
        return True
    def canBeBlockedBy(self, blocker):
        return True
    def canBlock(self):
        return not (self.tapped or self.in_combat)
    def canBlockAttacker(self, attacker):
        return True
    def clearCombatState(self):
        self.setCombat(False)    # XXX Should be a property that sends a signal when set
        if self.attacking:
            self.attacking = False
            self.send(AttackerClearedEvent())
            self.blocked = False
        elif self.blocking:
            self.blocking = False
            self.send(BlockerClearedEvent())
    def setAttacking(self):
        self.setCombat(True)
        self.tap()
        self.attacking = True
        self.send(AttackerDeclaredEvent())
    def setBlocked(self, blockers):
        if blockers:
            self.blocked = True
            self.send(AttackerBlockedEvent(), blockers=blockers)
    def setBlocking(self, attacker):
        self.setCombat(True)
        self.blocking = True
        self.send(BlockerDeclaredEvent(), attacker=attacker)
    def setCombat(self, in_combat):
        self.in_combat = in_combat
        if in_combat: self.send(CreatureInCombatEvent())
        else: self.send(CreatureCombatClearedEvent())
    def computeBlockCost(self):
        self.block_cost = ["0"]
        return True
    def payBlockCost(self):
        from Ability.Cost import MultipleCosts
        player = self.controller
        cost = MultipleCosts(self.block_cost)
        if cost.precompute(self.card, player) and cost.compute(self.card, player):
            cost.pay(self.card, player)
    def computeAttackCost(self):
        self.attack_cost = ["0"]
        return True
    def payAttackCost(self):
        from Ability.Cost import MultipleCosts
        player = self.controller
        cost = MultipleCosts(self.attack_cost)
        if cost.precompute(self.card, player) and cost.compute(self.card, player):
            cost.pay(self.card, player)
    def shouldDestroy(self):
        return self.__damage >= self.toughness and super(Creature, self).shouldDestroy()
    #def subrole_info(self):
    #    txt = ["%d/%d"%(self.base_power, self.base_toughness)]
    #    txt.append(str(self.PT_other_modifiers))
    #    txt.append(', '.join([str(c) for c in self.counters if hasattr(c,"power")]))
    #    txt.append(str(self.PT_static_modifiers))
    #    txt.append(str(self.PT_switch_modifiers))
    #    return '' #'P/T:\n'+'\n'.join(["6%s: %s"%(layer, mod) for layer, mod in zip("ABCDE", txt) if mod])

class Attachment(object):
    attached_abilities = property(fget=lambda self: self.abilities.attached())
    def activateAttachment(self):
        self.attached_to = None
        self.target_types = None
        #super(Attachment, self).activateRole()
    def deactivateRole(self):
        self.unattach()
        super(Attachment,self).deactivateRole()
    def set_target_type(self, target_type):
        # This is set by the aura playing ability, or the equip ability
        self.target_type = target_type
    def attach(self, target):
        if self.attached_to != None: self.unattach()
        self.attached_to = target
        self.attached_to.attachments.append(self.card)
        for ability in self.attached_abilities: ability.enable(self.card)
        self.send(AttachedEvent(), attached=self.attached_to)
        return True
    def unattach(self):
        if self.attached_to:
            for ability in self.attached_abilities: ability.disable()
            self.attached_to.attachments.remove(self.card)
            self.send(UnAttachedEvent(), unattached=self.attached_to)
        self.attached_to = None
    def attachedLeavingPlay(self):
        for ability in self.attached_abilities: ability.disable()
        self.send(UnAttachedEvent(), unattached=self.attached_to)
        self.attached_to = None
    def isValidAttachment(self):
        attachment = self.attached_to
        return (attachment and str(attachment.zone) == "play" and self.target_type.match(attachment) and attachment.canBeAttachedBy(self.card))
