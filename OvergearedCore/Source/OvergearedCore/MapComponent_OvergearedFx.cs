using System.Collections.Generic;
using UnityEngine;
using Verse;
using Verse.Sound;

namespace OvergearedCore
{
    public class ActiveSkillInstance
    {
        public SkillFxDef fx;
        public Pawn caster;
        public LocalTargetInfo target;
        public Vector3 origin;
        public Vector3 targetPos;
        public float facingSign;
        public float startRealTime;
        public int nextHitIdx;
        public float baseDamage;
        public DamageDef damageDef;
        public bool finished;
    }

    public class ActiveHitBurst
    {
        public SkillFxDef fx;
        public Vector3 pos;
        public float startRealTime;
        public float scale = 1f;
    }

    public class PawnAfterimage
    {
        public Vector3 pos;
        public float bornRealTime;
        public float life = 0.35f;
        public Color tint = new Color(0.75f, 0.30f, 1.0f, 0.55f);
    }

    /// <summary>
    /// MapComponent driving world-space multi-frame SkillFx sequences, screen-darken dramatic veils,
    /// camera shake, multi-strike damage bursts, and pawn afterimages cleanly inside RimWorld 1.7.
    /// </summary>
    public class MapComponent_OvergearedFx : MapComponent
    {
        private readonly List<ActiveSkillInstance> _active = new List<ActiveSkillInstance>();
        private readonly List<ActiveHitBurst> _hits = new List<ActiveHitBurst>();
        private readonly List<PawnAfterimage> _ghosts = new List<PawnAfterimage>();
        private float _darkenAlpha;
        private Material _dimMat;

        public MapComponent_OvergearedFx(Map map) : base(map) { }

        public void TriggerSkill(SkillFxDef fx, Pawn caster, LocalTargetInfo target, float baseDamage, DamageDef dmgDef)
        {
            if (fx == null || caster == null || !caster.Spawned) return;
            Vector3 cPos = caster.DrawPos;
            Vector3 tPos = target.IsValid ? target.CenterVector3 : (cPos + Vector3.right * 1.4f);
            float fSign = (tPos.x >= cPos.x) ? 1f : -1f;

            _active.Add(new ActiveSkillInstance
            {
                fx = fx,
                caster = caster,
                target = target,
                origin = cPos,
                targetPos = tPos,
                facingSign = fSign,
                startRealTime = Time.realtimeSinceStartup,
                nextHitIdx = 0,
                baseDamage = baseDamage,
                damageDef = dmgDef ?? DamageDefOf.Cut,
            });

            _darkenAlpha = Mathf.Max(_darkenAlpha, fx.screenDarken);
            fx.castSound?.PlayOneShot(new TargetInfo(caster.Position, map));

            if (fx.spawnAfterimages)
            {
                for (int i = 1; i <= 3; i++)
                {
                    Vector3 gp = Vector3.Lerp(cPos, tPos, i * 0.22f);
                    _ghosts.Add(new PawnAfterimage { pos = gp, bornRealTime = Time.realtimeSinceStartup + i * 0.04f });
                }
            }
        }

        public override void MapComponentUpdate()
        {
            base.MapComponentUpdate();
            float now = Time.realtimeSinceStartup;

            if (_darkenAlpha > 0.01f && _active.Count > 0)
            {
                DrawScreenDarken(_darkenAlpha * 0.72f);
            }
            else
            {
                _darkenAlpha = Mathf.Max(0f, _darkenAlpha - Time.deltaTime * 1.8f);
                if (_darkenAlpha > 0.01f) DrawScreenDarken(_darkenAlpha * 0.72f);
            }

            // Update & draw main multi-frame SkillFx sequences
            for (int i = _active.Count - 1; i >= 0; i--)
            {
                var inst = _active[i];
                float elapsedMs = (now - inst.startRealTime) * 1000f;
                int frame = Mathf.FloorToInt(elapsedMs / Mathf.Max(16f, inst.fx.frameDelayMs));

                while (inst.nextHitIdx < inst.fx.hitFrames.Count && frame >= inst.fx.hitFrames[inst.nextHitIdx])
                {
                    ApplyStrikeHit(inst, inst.nextHitIdx, now);
                    inst.nextHitIdx++;
                }

                if (frame >= inst.fx.frameCount)
                {
                    _active.RemoveAt(i);
                    continue;
                }

                Material mat = inst.fx.GetFrameMat(frame);
                if (mat != null)
                {
                    Vector3 center = inst.fx.centeredOnCaster ? inst.origin : Vector3.Lerp(inst.origin, inst.targetPos, 0.55f);
                    Vector3 pos = new Vector3(
                        center.x + (0.5f - inst.fx.anchor.x) * inst.fx.size.x * inst.facingSign,
                        AltitudeLayer.MoteOverhead.AltitudeFor() + 0.05f,
                        center.z + (inst.fx.anchor.y - 0.5f) * inst.fx.size.y
                    );
                    Vector3 scl = new Vector3(inst.fx.size.x * inst.facingSign, 1f, inst.fx.size.y);
                    Matrix4x4 mtx = Matrix4x4.TRS(pos, Quaternion.identity, scl);
                    Graphics.DrawMesh(MeshPool.plane10, mtx, mat, 0);
                }
            }

            // Draw Hit impact bursts
            for (int i = _hits.Count - 1; i >= 0; i--)
            {
                var hb = _hits[i];
                int hFrame = Mathf.FloorToInt((now - hb.startRealTime) * 1000f / 45f);
                if (hFrame >= hb.fx.hitFrameCount)
                {
                    _hits.RemoveAt(i);
                    continue;
                }
                Material hm = hb.fx.GetHitFrameMat(hFrame);
                if (hm != null)
                {
                    Vector3 pos = new Vector3(hb.pos.x, AltitudeLayer.MoteOverhead.AltitudeFor() + 0.12f, hb.pos.z);
                    Matrix4x4 mtx = Matrix4x4.TRS(pos, Quaternion.identity, new Vector3(hb.fx.hitSize.x * hb.scale, 1f, hb.fx.hitSize.y * hb.scale));
                    Graphics.DrawMesh(MeshPool.plane10, mtx, hm, 0);
                }
            }

            // Draw & clean pawn afterimages
            for (int i = _ghosts.Count - 1; i >= 0; i--)
            {
                var g = _ghosts[i];
                float age = now - g.bornRealTime;
                if (age >= g.life)
                {
                    _ghosts.RemoveAt(i);
                    continue;
                }
                if (age >= 0f)
                {
                    float alpha = (1f - age / g.life) * g.tint.a;
                    if (_ghostMat == null)
                        _ghostMat = SolidColorMaterials.SimpleSolidColorMaterial(new Color(0.80f, 0.32f, 1.0f, 1f));
                    _ghostMat.color = new Color(g.tint.r, g.tint.g, g.tint.b, alpha);
                    Vector3 gPos = new Vector3(g.pos.x, AltitudeLayer.MoteOverhead.AltitudeFor() - 0.02f, g.pos.z + 0.15f);
                    Matrix4x4 gMtx = Matrix4x4.TRS(gPos, Quaternion.identity, new Vector3(0.85f, 1f, 1.15f));
                    Graphics.DrawMesh(MeshPool.plane10, gMtx, _ghostMat, 0);
                }
            }
        }

        private Material _ghostMat;

        private void ApplyStrikeHit(ActiveSkillInstance inst, int hitIdx, float now)
        {
            float mult = (hitIdx < inst.fx.damageMultipliers.Count) ? inst.fx.damageMultipliers[hitIdx] : 1.0f;
            Thing primaryTarget = inst.target.Thing;
            Vector3 impactPos = inst.target.IsValid ? inst.target.CenterVector3 : inst.targetPos;

            if (inst.fx.aoeRadius > 0.1f)
            {
                // True square/grid AoE blast (e.g. aoeRadius 2.5 => 5x5 tile explosion centered on target!)
                IntVec3 centerCell = impactPos.ToIntVec3();
                int halfSpan = Mathf.Max(1, Mathf.FloorToInt(inst.fx.aoeRadius));
                var pawns = map.mapPawns.AllPawnsSpawned;
                for (int pi = pawns.Count - 1; pi >= 0; pi--)
                {
                    Pawn p = pawns[pi];
                    if (p == null || !p.Spawned || p.Dead || p == inst.caster) continue;
                    if (p != primaryTarget && p.Faction == inst.caster.Faction) continue;
                    if (Mathf.Abs(p.Position.x - centerCell.x) <= halfSpan && Mathf.Abs(p.Position.z - centerCell.z) <= halfSpan)
                    {
                        var dinfo = new DamageInfo(inst.damageDef, inst.baseDamage * mult, 0.50f, inst.caster.DrawPos.AngleToFlat(p.DrawPos), inst.caster);
                        p.TakeDamage(dinfo);
                    }
                }
            }
            else if (primaryTarget != null && primaryTarget.Spawned && !primaryTarget.Destroyed)
            {
                var dinfo = new DamageInfo(inst.damageDef, inst.baseDamage * mult, 0.45f, inst.caster.DrawPos.AngleToFlat(primaryTarget.DrawPos), inst.caster);
                primaryTarget.TakeDamage(dinfo);
            }
            _hits.Add(new ActiveHitBurst
            {
                fx = inst.fx,
                pos = impactPos,
                startRealTime = now,
                scale = Mathf.Max(0.85f, mult),
            });
            inst.fx.hitSound?.PlayOneShot(new TargetInfo(inst.targetPos.ToIntVec3(), map));
            Find.CameraDriver?.shaker.DoShake(inst.fx.cameraShake * mult);
        }

        private void DrawScreenDarken(float alpha)
        {
            if (_dimMat == null)
                _dimMat = SolidColorMaterials.SimpleSolidColorMaterial(new Color(0.03f, 0.01f, 0.06f, 1f));
            _dimMat.color = new Color(0.03f, 0.01f, 0.06f, Mathf.Clamp01(alpha));
            Vector3 cam = Find.CameraDriver.MapPosition.ToVector3ShiftedWithAltitude(AltitudeLayer.MoteLow);
            Matrix4x4 mtx = Matrix4x4.TRS(cam, Quaternion.identity, new Vector3(95f, 1f, 95f));
            Graphics.DrawMesh(MeshPool.plane10, mtx, _dimMat, 0);
        }
    }
}
