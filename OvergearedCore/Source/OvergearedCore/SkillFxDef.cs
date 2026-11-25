using System.Collections.Generic;
using UnityEngine;
using Verse;

namespace OvergearedCore
{
    /// <summary>
    /// Fairycore-style multi-frame sprite sequence SkillFx definition + combat timing metadata.
    /// </summary>
    public class SkillFxDef : Def
    {
        public string texFolder;
        public string hitFolder;
        public int frameCount = 16;
        public int hitFrameCount = 8;
        public int frameDelayMs = 55;
        public Vector2 size = new Vector2(4.6f, 3.6f);
        public Vector2 hitSize = new Vector2(2.2f, 2.2f);
        public Vector2 anchor = new Vector2(0.48f, 0.55f);
        public bool additive = false;
        public float screenDarken = 0.45f;
        public float cameraShake = 0.35f;
        public int hitStopTicks = 8;
        public bool spawnAfterimages = false;
        public bool centeredOnCaster = false;
        public float aoeRadius = 0f;
        public List<int> hitFrames = new List<int>();
        public List<float> damageMultipliers = new List<float>();
        public SoundDef castSound;
        public SoundDef hitSound;

        [Unsaved] private Material[] _mainMats;
        [Unsaved] private Material[] _hitMats;

        public Material GetFrameMat(int index)
        {
            if (_mainMats == null)
            {
                _mainMats = LoadSequence(texFolder, frameCount, additive);
            }
            if (_mainMats.Length == 0) return null;
            return _mainMats[Mathf.Clamp(index, 0, _mainMats.Length - 1)];
        }

        public Material GetHitFrameMat(int index)
        {
            if (_hitMats == null && !string.IsNullOrEmpty(hitFolder))
            {
                _hitMats = LoadSequence(hitFolder, hitFrameCount, true);
            }
            if (_hitMats == null || _hitMats.Length == 0) return null;
            return _hitMats[Mathf.Clamp(index, 0, _hitMats.Length - 1)];
        }

        private static Material[] LoadSequence(string folder, int count, bool isAdd)
        {
            if (string.IsNullOrEmpty(folder) || count <= 0) return System.Array.Empty<Material>();
            var shader = isAdd ? ShaderDatabase.MoteGlow : ShaderDatabase.Transparent;
            var arr = new Material[count];
            for (int i = 0; i < count; i++)
            {
                string path = $"{folder}/{i:D2}";
                Texture2D tex = ContentFinder<Texture2D>.Get(path, reportFailure: false);
                if (tex != null)
                {
                    arr[i] = MaterialPool.MatFrom(tex, shader, Color.white);
                }
            }
            return arr;
        }
    }

    public class CompProperties_OvergearedWeaponSkills : CompProperties
    {
        public List<SkillFxDef> skills = new List<SkillFxDef>();
        public int cooldownTicks = 180;

        public CompProperties_OvergearedWeaponSkills()
        {
            compClass = typeof(CompOvergearedWeaponSkills);
        }
    }
}
