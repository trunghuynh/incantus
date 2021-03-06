import copy
from engine.GameEvent import AbilityAnnounced, AbilityCanceled, AbilityCountered, AbilityResolved, TimestepEvent
from Ability import Ability

__all__ = ["StackAbility"]

class StackAbility(Ability):
    def __init__(self, effects, txt=''):
        self.effect_generator = effects
        if not txt and effects.__doc__: txt = effects.__doc__
        self.controller = None
        super(StackAbility, self).__init__(txt)
    def timestep(self):
        self.source.send(TimestepEvent())
    def announce(self):
        self.preannounce()
        if self.do_announce():
            self.played()
            self.timestep()
            return True
        else:
            self.canceled()
            return False
    def preannounce(self):
        self._targets = []
        self.source.send(AbilityAnnounced(), ability=self)
    def canceled(self): self.source.send(AbilityCanceled(), ability=self)
    def do_announce(self): raise NotImplementedException()
    def played(self): self.controller.stack.push(self)
    def targets_from_effects(self): raise NotImplementedException()
    def get_targets(self):
        targets = self.targets_from_effects()
        if not isinstance(targets, tuple): targets = (targets,)
        if all((target.get(self.source) for target in targets)):
            self._targets = targets
            return True
        else: return False
    def resolve(self):
        if any([target.check_target(self.source) for target in self._targets]):
            targets = tuple((target.get_targeted() for target in self._targets))
            if len(targets) == 1: targets = targets[0]
            self.effects.send(targets)
            self.timestep()
            for _ in self.effects:
                self.timestep()
            self.resolved()
        else: self.countered()
        del self.effects
    def resolved(self):
        self.timestep()
        self.source.send(AbilityResolved())
    def can_be_countered(self): return True
    def counter(self):
        if self.can_be_countered():
            self.controller.stack.counter(self)
            self.countered()
            return True
        else: return False
    def countered(self): self.source.send(AbilityCountered())
