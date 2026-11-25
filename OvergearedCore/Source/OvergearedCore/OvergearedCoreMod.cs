using HarmonyLib;
using Verse;

namespace OvergearedCore
{
    public class OvergearedCoreMod : Mod
    {
        public OvergearedCoreMod(ModContentPack content) : base(content)
        {
            var harmony = new Harmony("local.overgeared.core");
            harmony.PatchAll();
            Log.Message("[OvergearedCore] Initialized multi-frame SkillFx animation engine.");
        }
    }
}
