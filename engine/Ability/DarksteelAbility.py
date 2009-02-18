from game.Match import isArtifactCreature
from TriggeredAbility import TriggeredAbility, source_match
from Trigger import EnterFromTrigger
from Target import Target
from CiPAbility import CiP, CiPAbility
from Counters import PowerToughnessCounter

def modular(n):
    txt = "Modular %d"%n
    def enterPlayWith(self):
        self.add_counters(PowerToughnessCounter(1,1), number=n)
    def effects(source):
        yield CiP(source, enterPlayWith, txt=txt)
    cip = CiPAbility(effects, txt=txt, keyword="modular")

    def effects(controller, source):
        target = yield Target(isArtifactCreature, msg="Target Artifact Creature for %s"%source)
        if controller.you_may("move all +1/+1 counters from %s to target"%source.name):
            target.add_counters(PowerToughnessCounter(1,1), number=source.num_counters("+1+1"))
        yield
    triggered = TriggeredAbility(EnterFromTrigger("graveyard", "play", player="any"),
            condition=source_match,
            effects=effects,
            txt='')
    return (cip, triggered)