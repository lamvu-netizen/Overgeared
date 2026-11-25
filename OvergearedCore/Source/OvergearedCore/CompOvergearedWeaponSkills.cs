using System.Collections.Generic;
using RimWorld;
using UnityEngine;
using Verse;

namespace OvergearedCore
{
    public class CompOvergearedWeaponSkills : ThingComp
    {
        public CompProperties_OvergearedWeaponSkills Props => (CompProperties_OvergearedWeaponSkills)props;
        private int _cooldownUntilTick;

        public bool IsOnCooldown => Find.TickManager.TicksGame < _cooldownUntilTick;

        public void StartCooldown()
        {
            _cooldownUntilTick = Find.TickManager.TicksGame + Props.cooldownTicks;
        }

        public override IEnumerable<Gizmo> CompGetEquippedGizmosExtra()
        {
            Pawn pawn = ParentHolder is Pawn_EquipmentTracker eq ? eq.pawn : null;
            if (pawn == null || !pawn.IsColonistPlayerControlled || Props.skills == null) yield break;

            foreach (var fx in Props.skills)
            {
                if (fx == null) continue;
                int ticksLeft = Mathf.Max(0, _cooldownUntilTick - Find.TickManager.TicksGame);
                yield return new Command_Target
                {
                    defaultLabel = fx.label ?? fx.defName,
                    defaultDesc = $"Execute signature SkillFx: {fx.label} ({fx.hitFrames.Count}-Hit)",
                    targetingParams = TargetingParameters.ForAttackAny(),
                    disabled = ticksLeft > 0,
                    disabledReason = ticksLeft > 0 ? $"Cooldown: {ticksLeft / 60f:F1}s" : null,
                    action = target =>
                    {
                        var comp = pawn.Map?.GetComponent<MapComponent_OvergearedFx>();
                        if (comp != null)
                        {
                            _cooldownUntilTick = Find.TickManager.TicksGame + Props.cooldownTicks;
                            float dmg = parent.GetStatValue(StatDefOf.MeleeWeapon_AverageDPS) * 1.4f;
                            comp.TriggerSkill(fx, pawn, target, Mathf.Max(18f, dmg), DamageDefOf.Cut);
                        }
                    },
                };
            }
        }
    }
}
