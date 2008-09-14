from game.GameEvent import DeclareAttackersEvent, InvalidTargetEvent, EndTurnStepEvent
from game.Match import isCreature
from game.stacked_function import replace
from game.Decorators import comes_into_play, delayed_trigger
from ActivatedAbility import ActivatedAbility
from TriggeredAbility import TriggeredAbility
from CreatureAbility import haste
from Effects import until_end_of_turn, delay
from Target import NoTarget
from Trigger import Trigger, PhaseTrigger
from Counters import PowerToughnessCounter
from Cost import ManaCost
from Limit import sorcery

def exalted():
    def condition(source, sender, attackers):
        return sender.curr_player == source.controller and len(attackers) == 1
    def effects(controller, source, attackers):
        yield NoTarget()
        until_end_of_turn(attackers[0].augment_power_toughness(1, 1))
        yield
    return TriggeredAbility(Trigger(DeclareAttackersEvent()), condition, effects, zone="play", keyword='exalted')

def devour(value):
    @comes_into_play("Devour %d"%value)
    def ability():
        def enterPlayWith(source):
            cards = set()
            if source.controller.you_may("Sacrifice creatures to %s"%source.name):
                i = 0
                num_creatures = len(source.controller.play.get(isCreature))
                while i < num_creatures:
                    creature = source.controller.getTarget(isCreature, zone="play", controller=source.controller, required=False, prompt="Select any number of creatures to sacrifice: (%d selected so far)"%i)
                    if creature == False: break
                    elif not creature in cards:
                        cards.add(creature)
                        i += 1
                    else: source.controller.send(InvalidTargetEvent(), target=creature)
                for card in cards: source.controller.sacrifice(card)
                if cards: source.add_counters(PowerToughnessCounter(1, 1), len(cards)*value)
        return no_before, enterPlayWith
    return ability

def unearth(cost):
    if type(cost) == str: cost = ManaCost(cost)
    def effects(controller, source):
        yield cost
        yield NoTarget()
        source.move_to(controller.play)
        yield
        source.abilities.add(haste())

        @delayed_trigger(PhaseTrigger(EndTurnStepEvent()), txt="Remove this from the game at end of turn.")
        def d_trigger():
            def effects(controller, source):
                yield NoTarget()
                source.move_to(source.owner.removed)
                yield
            return no_condition, effects

        leave_play_condition = lambda self, zone, position="top": str(self.zone) == "play"
        def move_to(self, zone, position="top"):
            self.move_to(self.owner.removed)
        until_end_of_turn(delay(source, d_trigger), replace(source, "move_to", move_to, msg="%s - remove from game"%source.name, condition=leave_play_condition))
        yield
    return ActivatedAbility(effects, limit=sorcery, zone="graveyard", keyword="Unearth %s"%str(cost))