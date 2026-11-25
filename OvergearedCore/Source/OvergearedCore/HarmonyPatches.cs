using System;
using HarmonyLib;
using RimWorld;
using Verse;

namespace OvergearedCore
{
    /// <summary>
    /// Hooks RimWorld melee strikes so weapons carrying CompOvergearedWeaponSkills
    /// automatically unleash signature multi-frame SkillFx bursts when ready, plus manual gizmo casts.
    /// </summary>
    [HarmonyPatch(typeof(Verb_MeleeAttackDamage), "ApplyMeleeDamageToTarget")]
    public static class Patch_MeleeApplyDamage_TriggerSkillFx
    {
        private static readonly System.Random Rng = new System.Random();

        [HarmonyPostfix]
        public static void Postfix(Verb_MeleeAttackDamage __instance, LocalTargetInfo target)
        {
            Pawn caster = __instance?.CasterPawn;
            Thing weapon = __instance?.EquipmentSource;
            if (caster == null || weapon == null || caster.Map == null || !target.IsValid) return;

            var comp = weapon.TryGetComp<CompOvergearedWeaponSkills>();
            if (comp == null || comp.Props?.skills == null || comp.Props.skills.Count == 0) return;

            // Only auto-proc ~30% of swings when off cooldown so combat pacing feels deliberate & anime-like
            if (comp.IsOnCooldown || Rng.NextDouble() > 0.30) return;

            SkillFxDef fx = comp.Props.skills[Rng.Next(comp.Props.skills.Count)];
            var mapComp = caster.Map.GetComponent<MapComponent_OvergearedFx>();
            if (mapComp != null && fx != null)
            {
                comp.StartCooldown();
                float dmg = Math.Max(16f, weapon.GetStatValue(StatDefOf.MeleeWeapon_AverageDPS) * 1.15f);
                mapComp.TriggerSkill(fx, caster, target, dmg, DamageDefOf.Cut);
            }
        }
    }
}
