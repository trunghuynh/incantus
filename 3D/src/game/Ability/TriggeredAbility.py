from Ability import Ability
from Effects import robustApply

source_match = lambda source, card: source == card
sender_match = lambda source, sender: source == sender

class TriggeredStackAbility(Ability):
    triggered = True
    def __init__(self, effects, trigger_keys, txt=''):
        super(TriggeredStackAbility, self).__init__(effects, txt)
        self.trigger_keys = trigger_keys
    def do_announce(self):
        self.effects = robustApply(self.effect_generator, **self.trigger_keys)
        return self.get_targets()

class TriggeredAbility(object):
    enabled = property(fget=lambda self: self._status_count > 0)
    def __init__(self, triggers, condition, effects, expiry=-1, zone="play", txt='', keyword=''):
        if not (type(triggers) == list or type(triggers) == tuple): triggers=[triggers]
        self.triggers = triggers
        self.condition = condition
        self.effect_generator = effects
        self.expiry = expiry
        self.zone = zone
        if keyword and not txt: self.txt = keyword.capitalize()
        else: self.txt = txt
        self.keyword = keyword
        self._status_count = 0
    def toggle(self, val):
        if val:
            for trigger in self.triggers:
                trigger.setup_trigger(self.source,self.playAbility,self.condition,self.expiry)
        else:
            for trigger in self.triggers:
                trigger.clear_trigger()
    def enable(self, source):
        self.source = source
        self._status_count += 1
        if self._status_count == 1: self.toggle(True)
    def disable(self):
        self._status_count -= 1
        if self._status_count == 0: self.toggle(False)
    def playAbility(self, **trigger_keys):
        player = self.source.controller
        trigger_keys["controller"] = player
        player.stack.add_triggered(TriggeredStackAbility(self.effect_generator, trigger_keys, txt=self.txt), self.source)
    def copy(self):
        return TriggeredAbility([t.copy() for t in self.triggers], self.condition, self.effect_generator, self.expiry, self.zone, self.txt)
    def __str__(self):
        return self.txt

class SpecialTriggeredAbility(TriggeredAbility):
    def __init__(self, triggers, condition, effects, special_funcs, expiry=-1, zone="play", txt='', keyword=''):
        super(SpecialTriggeredAbility, self).__init__(triggers, condition, effects, expiry, zone, txt, keyword)
        self.buildup, self.teardown = special_funcs
    def toggle(self, val):
        if val: self.buildup(self.source)
        else: self.teardown(self.source)
        super(SpecialTriggeredAbility, self).toggle(val)
