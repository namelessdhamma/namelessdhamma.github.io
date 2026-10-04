using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Text;
using System.Reflection;
using OpenUtau.Api;
using OpenUtau.Classic;
using OpenUtau.Core;
using OpenUtau.Core.Render;
using OpenUtau.Core.Format;
using OpenUtau.Core.Ustx;
using OpenUtau.Core.Util;
using OpenUtau.Core.DiffSinger;
using Xunit;

namespace OpenUtau.Test.Core.DiffSinger {
    public class GGVfsUfrOpenUtauQcTest {
        static void RegisterBaseExpressions(UProject project) {
            project.RegisterExpression(new UExpressionDescriptor("engine", "eng", 0, 100, 0) { options = new[] { "" } });
            project.RegisterExpression(new UExpressionDescriptor("volume", "vol", 0, 100, 100));
            project.RegisterExpression(new UExpressionDescriptor("velocity", "vel", 0, 200, 100));
            project.RegisterExpression(new UExpressionDescriptor("modulation", "mod", 0, 100, 0));
            project.RegisterExpression(new UExpressionDescriptor("direct", "dir", 0, 100, 0));
            project.RegisterExpression(new UExpressionDescriptor("shift", "shft", -24, 24, 0));
            project.RegisterExpression(new UExpressionDescriptor("attack", "atk", 0, 100, 100));
            project.RegisterExpression(new UExpressionDescriptor("decay", "dec", 0, 100, 100));
            project.RegisterExpression(new UExpressionDescriptor("dynamics (curve)", Ustx.DYN, -240, 120, 0) { type = UExpressionType.Curve });
            project.RegisterExpression(new UExpressionDescriptor("tension (curve)", Ustx.TENC, -100, 100, 0) { type = UExpressionType.Curve });
            project.RegisterExpression(new UExpressionDescriptor("breathiness (curve)", Ustx.BREC, -100, 100, 0) { type = UExpressionType.Curve });
            project.RegisterExpression(new UExpressionDescriptor("gender (curve)", Ustx.GENC, -100, 100, 0) { type = UExpressionType.Curve });
            project.RegisterExpression(new UExpressionDescriptor("voicing (curve)", Ustx.VOIC, 0, 100, 100) { type = UExpressionType.Curve });
        }

        static void WaitFor(Func<bool> condition, int timeoutMs, string failure) {
            var deadline = Environment.TickCount64 + timeoutMs;
            while (Environment.TickCount64 < deadline) {
                if (condition()) return;
                Thread.Sleep(25);
            }
            Assert.True(condition(), failure);
        }

        static string ExceptionChain(Exception? e) {
            var parts = new List<string>();
            for (var cur = e; cur != null; cur = cur.InnerException) {
                parts.Add(cur.GetType().Name + ": " + cur.Message);
            }
            return string.Join(" <- ", parts);
        }

        static int ApplyGeneratedPitch(RenderPhrase phrase, RenderPitchResult predicted) {
            if (predicted == null || predicted.ticks == null || predicted.tones == null) {
                return 0;
            }
            int n = Math.Min(predicted.ticks.Length, predicted.tones.Length);
            int changed = 0;
            int i = 0;
            while (i < n) {
                bool Valid(int k) =>
                    k >= 0 && k < n &&
                    predicted.tones[k] >= 0 &&
                    (predicted.voiced == null || k >= predicted.voiced.Length || predicted.voiced[k]);
                while (i < n && !Valid(i)) i++;
                if (i >= n) break;
                int start = i;
                while (i + 1 < n && Valid(i + 1)) i++;
                int end = i;
                if (end > start) {
                    int k = start;
                    for (int j = 0; j < phrase.pitches.Length; j++) {
                        float tick = -phrase.leading + j * 5;
                        if (tick < predicted.ticks[start] || tick > predicted.ticks[end]) continue;
                        while (k < end - 1 && predicted.ticks[k + 1] < tick) k++;
                        int k1 = Math.Min(k + 1, end);
                        float x0 = predicted.ticks[k];
                        float x1 = predicted.ticks[k1];
                        float tone = x1 <= x0
                            ? predicted.tones[k]
                            : predicted.tones[k] + (predicted.tones[k1] - predicted.tones[k])
                                * ((tick - x0) / (x1 - x0));
                        phrase.pitches[j] = tone * 100f;
                        changed++;
                    }
                }
                i++;
            }
            return changed;
        }

        static void ApplyHumanProsody(RenderPhrase phrase, string variant) {
            if (!(variant is "human_a" or "human_b" or "human_c")) return;
            // Performance editing only: native DiffSinger pitch is kept, then a sparse,
            // smooth OpenUtau-style pitch deviation is layered on top.
            float[] xs = { 0f, .10f, .23f, .36f, .50f, .64f, .78f, .90f, 1f };
            float[] ys = variant switch {
                "human_a" => new float[] { -6, 8, -12, 15, -8, 11, -14, 7, -5 },
                "human_b" => new float[] { -10, 14, -18, 24, -12, 18, -22, 11, -8 },
                _ => new float[] { -14, 18, -26, 32, -16, 24, -30, 15, -10 },
            };
            int n = phrase.pitches.Length;
            if (n < 2) return;
            for (int j = 0; j < n; j++) {
                float u = j / (float)(n - 1);
                int k = 0;
                while (k + 1 < xs.Length - 1 && xs[k + 1] < u) k++;
                float x0 = xs[k], x1 = xs[k + 1];
                float y0 = ys[k], y1 = ys[k + 1];
                float t = x1 <= x0 ? 0 : (u - x0) / (x1 - x0);
                // Smoothstep prevents mechanical corners between anchors.
                t = t * t * (3f - 2f * t);
                phrase.pitches[j] += y0 + (y1 - y0) * t;
            }
        }

        static void ApplySingerPhysics(RenderPhrase phrase, string variant) {
            if (!(variant is "singer_a" or "singer_b" or "singer_c")) return;
            int level = variant == "singer_a" ? 1 : variant == "singer_b" ? 2 : 3;
            if (phrase.pitches.Length < 2 || phrase.notes.Length == 0) return;

            float prep = level == 1 ? 14f : level == 2 ? 19f : 24f;
            float over = level == 1 ? 22f : level == 2 ? 29f : 34f;
            float fine = level == 1 ? 1.7f : level == 2 ? 2.3f : 2.8f;

            for (int j = 0; j < phrase.pitches.Length; j++) {
                float tick = -phrase.leading + j * 5;
                float delta = 0f;

                // Context-sensitive transition physics: preparation before a move,
                // overshoot just after it, then a damped settle toward the target.
                for (int i = 1; i < phrase.notes.Length; i++) {
                    var prev = phrase.notes[i - 1];
                    var next = phrase.notes[i];
                    float transition = next.position;
                    float direction = Math.Sign(next.tone - prev.tone);
                    if (direction == 0) continue;

                    float prepStart = transition - 58f;
                    if (tick >= prepStart && tick < transition) {
                        float u = (tick - prepStart) / (transition - prepStart);
                        delta += -direction * prep * (float)Math.Sin(Math.PI * u);
                    }
                    float settleEnd = transition + 105f;
                    if (tick >= transition && tick <= settleEnd) {
                        float u = (tick - transition) / (settleEnd - transition);
                        // Peak early, then settle smoothly instead of a linear bend.
                        delta += direction * over * (float)(Math.Sin(Math.PI * Math.Min(1.0, u * 1.45)) * Math.Exp(-1.35 * u));
                    }
                }

                // A human singer rarely parks perfectly at one F0. Each sustained note
                // has a gentle rise/fall shaped by its semantic/metric position.
                var note = phrase.notes.FirstOrDefault(n => tick >= n.position && tick <= n.end);
                if (note != null && note.duration > 0) {
                    float u = Math.Clamp((tick - note.position) / note.duration, 0f, 1f);
                    float arch = (float)Math.Sin(Math.PI * u);
                    float semantic = note.lyric switch {
                        "Я" => 3f,
                        "говорил" => 8f,
                        "не" => 11f,
                        "с" => -2f,
                        "ним" => -7f,
                        _ => 0f,
                    };
                    delta += arch * semantic * (0.75f + 0.15f * level);

                    // Deterministic fine fluctuation: low amplitude, non-repeating,
                    // and subordinate to the musical contour (not random jitter).
                    double ms = note.positionMs + u * note.durationMs;
                    double sec = ms / 1000.0;
                    delta += fine * (float)(
                        0.55 * Math.Sin(2 * Math.PI * 10.9 * sec + 0.31) +
                        0.30 * Math.Sin(2 * Math.PI * 13.7 * sec + 1.17) +
                        0.15 * Math.Sin(2 * Math.PI * 17.3 * sec + 2.09));
                }

                phrase.pitches[j] += delta;
            }
        }

        [Fact]
        public void RenderUfrVoiceWithOfficialRussianPhonemizer() {
            var singersRoot = Environment.GetEnvironmentVariable("OPENUTAU_TEST_SINGERS");
            var outDir = Environment.GetEnvironmentVariable("GG_VFS_OUT");
            Assert.False(string.IsNullOrWhiteSpace(singersRoot));
            Assert.False(string.IsNullOrWhiteSpace(outDir));
            Directory.CreateDirectory(outDir!);

            ThreadGuard.SetUiThread(Thread.CurrentThread);
            DocManager.Inst.CommandSink = _ => { };
            Directory.CreateDirectory(PathManager.Inst.CachePath);
            Preferences.Default.DiffSingerTensorCache = false;
            Preferences.Default.AdditionalSingerPath = singersRoot!;
            int renderSteps = 30;
            int.TryParse(Environment.GetEnvironmentVariable("GG_VFS_STEPS"), out renderSteps);
            if (renderSteps <= 0) renderSteps = 30;
            Preferences.Default.DiffSingerSteps = renderSteps;
            Preferences.Default.DiffSingerStepsVariance = Math.Max(20, renderSteps / 2);
            Preferences.Default.DiffSingerStepsPitch = 12;
            Preferences.Default.DiffSingerDepth = 1.0;
            Preferences.Default.DiffSingerMergeNearbyPhrases = true;

            var dsconfigPath = Path.Combine(singersRoot!, "dsconfig.yaml");
            Assert.True(File.Exists(dsconfigPath), "No root dsconfig.yaml found in UFR singer bank.");
            var bankDir = singersRoot!;
            var acousticConfig = OpenUtau.Core.Yaml.DefaultDeserializer.Deserialize<DsConfig>(
                File.ReadAllText(Path.Combine(bankDir, "dsconfig.yaml"), Encoding.UTF8));
            var speakerHint = Environment.GetEnvironmentVariable("GG_VFS_SPEAKER_HINT") ?? "";
            var chosenSpeaker = acousticConfig.speakers?
                .FirstOrDefault(x => !string.IsNullOrWhiteSpace(speakerHint) && x.Contains(speakerHint, StringComparison.OrdinalIgnoreCase))
                ?? acousticConfig.speakers?.FirstOrDefault(x => x.Contains("core", StringComparison.OrdinalIgnoreCase))
                ?? acousticConfig.speakers?.FirstOrDefault(x => x.Contains("natural", StringComparison.OrdinalIgnoreCase))
                ?? acousticConfig.speakers?.FirstOrDefault();
            Assert.False(string.IsNullOrWhiteSpace(chosenSpeaker), "UFR singer config exposed no speaker embeddings.");

            var voicebank = new Voicebank {
                BasePath = singersRoot!,
                File = Path.Combine(bankDir, "character.txt"),
                Name = "UFR — direct OpenUtau Russian QC",
                Id = Path.GetFileName(bankDir),
                SingerType = USingerType.DiffSinger,
                TextFileEncoding = Encoding.UTF8,
            };
            voicebank.Subbanks.Add(new Subbank {
                Color = string.IsNullOrWhiteSpace(speakerHint) ? "Core" : speakerHint,
                Prefix = "",
                Suffix = chosenSpeaker!,
                ToneRanges = new[] { "C1-C7" },
            });
            var singer = (USinger)new DiffSingerSinger(voicebank);
            Assert.True(singer.Found && singer.Loaded, $"Direct DiffSinger bank failed: {string.Join("; ", singer.Errors)}");

            var variant = (Environment.GetEnvironmentVariable("GG_VFS_VARIANT") ?? "native").Trim().ToLowerInvariant();
            var project = new UProject();
            project.tempos.Clear();
            project.tempos.Add(new UTempo(0, variant switch {
                "clear_soft" => 80,
                "clear" => 80,
                "clear_warm" => 80,
                "clear_lively" => 80,
                "relax_a" => 78,
                "relax_b" => 78,
                "relax_c" => 76,
                "relax_d" => 76,
                "human_a" => 76,
                "human_b" => 75,
                "human_c" => 74,
                "singer_a" => 74,
                "singer_b" => 72,
                "singer_c" => 70,
                _ => 80,
            }));
            project.timeAxis.BuildSegments(project);
            RegisterBaseExpressions(project);

            var renderer = new DiffSingerRenderer();
            var track = project.tracks[0];
            track.TrackNo = 0;
            track.TrackName = "GG-VFS UFR OpenUtau QC";
            track.Singer = singer;
            track.RendererSettings.renderer = Renderers.DIFFSINGER;
            track.RendererSettings.Renderer = renderer;
            track.Phonemizer = new DiffSingerRussianPhonemizer();

            foreach (var descriptor in renderer.GetSuggestedExpressions(singer, track.RendererSettings)) {
                if (!project.expressions.ContainsKey(descriptor.abbr)) {
                    project.RegisterExpression(descriptor);
                }
            }
            track.RendererSettings.Validate(track);

            var part = new UVoicePart {
                name = "VFS UFR pronunciation QC",
                trackNo = 0,
                position = 0,
            };
            project.parts.Add(part);

            // Exact QC phrase. One lexical word per note lets the official RU phonemizer
            // own every internal phoneme and its relative timing.
            string[] lyrics = { "Я", "говорил", "не", "с", "ним" };
            int[] tones = variant switch {
                "singer_a" => new[] { 57, 59, 62, 60, 57 },
                "singer_b" => new[] { 57, 60, 63, 60, 57 },
                "singer_c" => new[] { 56, 59, 62, 60, 56 },
                _ => new[] { 57, 59, 60, 59, 57 },
            };
            int[] durations = variant switch {
                "clear_soft" =>   new[] { 580, 1160, 500, 220, 920 },
                "clear" =>        new[] { 580, 1160, 500, 220, 920 },
                "clear_warm" =>   new[] { 580, 1160, 500, 220, 920 },
                "clear_lively" => new[] { 580, 1160, 500, 220, 920 },
                "relax_a" =>      new[] { 600, 1210, 520, 230, 960 },
                "relax_b" =>      new[] { 610, 1240, 530, 230, 980 },
                "relax_c" =>      new[] { 620, 1260, 540, 240, 1000 },
                "relax_d" =>      new[] { 630, 1280, 550, 240, 1020 },
                "human_a" =>      new[] { 610, 1340, 500, 205, 1065 },
                "human_b" =>      new[] { 625, 1370, 470, 195, 1090 },
                "human_c" =>      new[] { 600, 1410, 455, 185, 1120 },
                "singer_a" =>     new[] { 620, 1450, 500, 185, 1220 },
                "singer_b" =>     new[] { 610, 1500, 480, 175, 1280 },
                "singer_c" =>     new[] { 640, 1540, 455, 170, 1340 },
                _ =>              new[] { 580, 1160, 500, 220, 920 },
            };            int pos = 0;
            for (int i = 0; i < lyrics.Length; i++) {
                var note = project.CreateNote(tones[i], pos, durations[i]);
                note.lyric = lyrics[i];
                // All performance shaping stays inside OpenUtau's native note/vibrato model.
                if (lyrics[i] is "говорил" or "ним") {
                    if (variant == "singer_a") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 32 : 38;
                        note.vibrato.period = lyrics[i] == "говорил" ? 205 : 195;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 14 : 18;
                        note.vibrato.@in = 58;
                        note.vibrato.@out = 42;
                    } else if (variant == "singer_b") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 35 : 42;
                        note.vibrato.period = lyrics[i] == "говорил" ? 195 : 185;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 18 : 22;
                        note.vibrato.@in = 60;
                        note.vibrato.@out = 44;
                    } else if (variant == "singer_c") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 38 : 45;
                        note.vibrato.period = lyrics[i] == "говорил" ? 188 : 178;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 21 : 26;
                        note.vibrato.@in = 63;
                        note.vibrato.@out = 46;
                    } else if (variant == "human_a") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 16 : 20;
                        note.vibrato.period = lyrics[i] == "говорил" ? 370 : 350;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 4 : 5;
                        note.vibrato.@in = 68;
                        note.vibrato.@out = 54;
                    } else if (variant == "human_b") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 14 : 19;
                        note.vibrato.period = lyrics[i] == "говорил" ? 390 : 360;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 4 : 6;
                        note.vibrato.@in = 72;
                        note.vibrato.@out = 56;
                    } else if (variant == "human_c") {
                        note.vibrato.length = lyrics[i] == "говорил" ? 12 : 18;
                        note.vibrato.period = lyrics[i] == "говорил" ? 410 : 375;
                        note.vibrato.depth = lyrics[i] == "говорил" ? 3 : 6;
                        note.vibrato.@in = 75;
                        note.vibrato.@out = 58;
                    } else if (variant == "relax_a") {
                        note.vibrato.length = 24;
                        note.vibrato.period = 315;
                        note.vibrato.depth = 7;
                        note.vibrato.@in = 52;
                        note.vibrato.@out = 42;
                    } else if (variant == "relax_b") {
                        note.vibrato.length = 22;
                        note.vibrato.period = 330;
                        note.vibrato.depth = 6;
                        note.vibrato.@in = 58;
                        note.vibrato.@out = 45;
                    } else if (variant == "relax_c") {
                        note.vibrato.length = 20;
                        note.vibrato.period = 345;
                        note.vibrato.depth = 5;
                        note.vibrato.@in = 62;
                        note.vibrato.@out = 48;
                    } else if (variant == "relax_d") {
                        note.vibrato.length = 18;
                        note.vibrato.period = 360;
                        note.vibrato.depth = 4;
                        note.vibrato.@in = 66;
                        note.vibrato.@out = 52;
                    } else if (variant == "clear_soft") {
                        note.vibrato.length = 27;
                        note.vibrato.period = 305;
                        note.vibrato.depth = 8;
                        note.vibrato.@in = 44;
                        note.vibrato.@out = 40;
                    } else if (variant == "clear_warm") {
                        note.vibrato.length = 34;
                        note.vibrato.period = 270;
                        note.vibrato.depth = 13;
                        note.vibrato.@in = 38;
                        note.vibrato.@out = 34;
                    } else if (variant == "clear_lively") {
                        note.vibrato.length = 37;
                        note.vibrato.period = 250;
                        note.vibrato.depth = 15;
                        note.vibrato.@in = 34;
                        note.vibrato.@out = 31;
                    } else {
                        note.vibrato.length = 32;
                        note.vibrato.period = 280;
                        note.vibrato.depth = 11;
                        note.vibrato.@in = 40;
                        note.vibrato.@out = 35;
                    }
                }
                part.notes.Add(note);
                pos += durations[i];
            }
            part.Duration = pos + 480;

            // Native DiffSinger expression curves; no external/post-render DSP is used.
            void AddFlatCurve(string abbr, int value) {
                if (project.expressions.TryGetValue(abbr, out var descriptor)) {
                    var curve = new UCurve(descriptor);
                    curve.xs.AddRange(new[] { 0, part.Duration });
                    curve.ys.AddRange(new[] { value, value });
                    part.curves.Add(curve);
                }
            }
            void AddShapeCurve(string abbr, int[] xs, int[] ys) {
                if (xs.Length != ys.Length || xs.Length < 2) return;
                if (project.expressions.TryGetValue(abbr, out var descriptor)) {
                    var curve = new UCurve(descriptor);
                    curve.xs.AddRange(xs);
                    curve.ys.AddRange(ys);
                    part.curves.Add(curve);
                }
            }
            if (variant == "singer_a" || variant == "singer_b" || variant == "singer_c") {
                int level = variant == "singer_a" ? 1 : variant == "singer_b" ? 2 : 3;
                AddFlatCurve(DiffSingerUtils.VELC, level == 1 ? 121 : level == 2 ? 120 : 119);

                // Macro phrase arc: enter quietly, build through "говорил",
                // crest on "не", then relax through "с ним".
                var n0 = part.notes[0]; var n1 = part.notes[1]; var n2 = part.notes[2];
                var n3 = part.notes[3]; var n4 = part.notes[4];
                AddShapeCurve(Ustx.DYN,
                    new[] { n0.position, n0.position + n0.duration/2, n1.position,
                            n1.position + n1.duration/2, n2.position, n2.position + n2.duration/2,
                            n3.position, n4.position, n4.position + n4.duration/2, n4.end, part.Duration },
                    level == 1 ? new[] { -22, -10, -9, 4, 6, 12, -3, -8, -2, -18, -26 } :
                    level == 2 ? new[] { -26, -12, -10, 6, 8, 16, -4, -10, 0, -21, -30 } :
                                 new[] { -30, -14, -12, 8, 10, 20, -5, -12, 2, -24, -34 });
                AddShapeCurve(DiffSingerUtils.ENE,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n2.position + n2.duration/2, n3.position,
                            n4.position, n4.position + n4.duration/2, n4.end, part.Duration },
                    level == 1 ? new[] { -12, -8, -2, 0, 5, -5, -10, -5, -15, -18 } :
                    level == 2 ? new[] { -14, -9, 0, 2, 8, -6, -12, -5, -17, -20 } :
                                 new[] { -16, -10, 2, 4, 10, -7, -14, -4, -19, -22 });
                AddShapeCurve(DiffSingerUtils.PEXP,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.end, part.Duration },
                    level == 1 ? new[] { 80, 88, 96, 100, 86, 91, 76, 72 } :
                    level == 2 ? new[] { 78, 90, 100, 100, 84, 94, 74, 70 } :
                                 new[] { 76, 92, 100, 100, 82, 96, 72, 68 });
                AddShapeCurve(Ustx.TENC,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.end, part.Duration },
                    level == 1 ? new[] { -30, -24, -14, -8, -24, -28, -36, -38 } :
                    level == 2 ? new[] { -34, -26, -12, -5, -25, -30, -39, -41 } :
                                 new[] { -38, -28, -10, -2, -26, -32, -42, -44 });
                AddShapeCurve(Ustx.BREC,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.position + n4.duration/2, n4.end, part.Duration },
                    level == 1 ? new[] { 16, 12, 7, 5, 11, 12, 15, 21, 24 } :
                    level == 2 ? new[] { 18, 13, 7, 4, 12, 13, 17, 23, 26 } :
                                 new[] { 20, 14, 6, 3, 13, 14, 19, 25, 28 });
                AddShapeCurve(Ustx.VOIC,
                    new[] { n0.position, n1.position, n2.position, n3.position, n4.position, n4.end, part.Duration },
                    level == 1 ? new[] { 96, 98, 100, 95, 98, 94, 93 } :
                    level == 2 ? new[] { 95, 99, 100, 94, 98, 93, 92 } :
                                 new[] { 94, 99, 100, 93, 97, 92, 91 });
            } else if (variant == "human_a" || variant == "human_b" || variant == "human_c") {
                int level = variant == "human_a" ? 1 : variant == "human_b" ? 2 : 3;
                AddFlatCurve(DiffSingerUtils.VELC, level == 1 ? 122 : level == 2 ? 121 : 120);
                AddShapeCurve(DiffSingerUtils.PEXP,
                    new[] { 0, 500, 1150, 1850, 2450, part.Duration },
                    level == 1 ? new[] { 78, 86, 76, 88, 80, 74 } :
                    level == 2 ? new[] { 74, 88, 72, 91, 78, 70 } :
                                 new[] { 70, 90, 68, 94, 76, 66 });
                AddShapeCurve(DiffSingerUtils.ENE,
                    new[] { 0, 450, 1100, 1750, 2350, 3000, part.Duration },
                    level == 1 ? new[] { -9, -4, -7, -2, -8, -5, -11 } :
                    level == 2 ? new[] { -11, -4, -9, -1, -10, -5, -13 } :
                                 new[] { -13, -5, -11, 0, -12, -6, -15 });
                AddShapeCurve(Ustx.DYN,
                    new[] { 0, 500, 1200, 1900, 2500, 3100, part.Duration },
                    level == 1 ? new[] { -10, 4, -4, 8, -8, 2, -12 } :
                    level == 2 ? new[] { -14, 6, -6, 10, -10, 3, -16 } :
                                 new[] { -18, 8, -8, 12, -12, 4, -20 });
                AddShapeCurve(Ustx.TENC,
                    new[] { 0, 700, 1500, 2200, 3000, part.Duration },
                    level == 1 ? new[] { -25, -15, -23, -12, -22, -28 } :
                    level == 2 ? new[] { -30, -16, -28, -10, -26, -32 } :
                                 new[] { -34, -18, -32, -8, -30, -36 });
                AddShapeCurve(Ustx.BREC,
                    new[] { 0, 700, 1500, 2200, 3000, part.Duration },
                    level == 1 ? new[] { 12, 7, 11, 6, 10, 14 } :
                    level == 2 ? new[] { 15, 8, 14, 6, 12, 17 } :
                                 new[] { 18, 9, 16, 6, 14, 20 });
                AddShapeCurve(Ustx.VOIC,
                    new[] { 0, 900, 1800, 2700, part.Duration },
                    level == 1 ? new[] { 96, 99, 97, 98, 95 } :
                    level == 2 ? new[] { 95, 99, 96, 98, 94 } :
                                 new[] { 94, 99, 95, 97, 93 });
            } else             if (variant == "relax_a") {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 86);
                AddFlatCurve(DiffSingerUtils.ENE, -3);
                AddFlatCurve(Ustx.TENC, -8);
                AddFlatCurve(Ustx.BREC, 4);
                AddFlatCurve(Ustx.VOIC, 98);
            } else if (variant == "relax_b") {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 82);
                AddFlatCurve(DiffSingerUtils.ENE, -5);
                AddFlatCurve(Ustx.TENC, -14);
                AddFlatCurve(Ustx.BREC, 7);
                AddFlatCurve(Ustx.VOIC, 97);
            } else if (variant == "relax_c") {
                AddFlatCurve(DiffSingerUtils.VELC, 123);
                AddFlatCurve(DiffSingerUtils.PEXP, 78);
                AddFlatCurve(DiffSingerUtils.ENE, -7);
                AddFlatCurve(Ustx.TENC, -20);
                AddFlatCurve(Ustx.BREC, 10);
                AddFlatCurve(Ustx.VOIC, 96);
            } else if (variant == "relax_d") {
                AddFlatCurve(DiffSingerUtils.VELC, 122);
                AddFlatCurve(DiffSingerUtils.PEXP, 74);
                AddFlatCurve(DiffSingerUtils.ENE, -9);
                AddFlatCurve(Ustx.TENC, -26);
                AddFlatCurve(Ustx.BREC, 13);
                AddFlatCurve(Ustx.VOIC, 95);
            } else             if (variant == "clear_soft") {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 90);
                AddFlatCurve(DiffSingerUtils.ENE, -2);
            } else if (variant == "clear_warm") {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 92);
                AddFlatCurve(DiffSingerUtils.ENE, 2);
            } else if (variant == "clear_lively") {
                AddFlatCurve(DiffSingerUtils.VELC, 125);
                AddFlatCurve(DiffSingerUtils.PEXP, 94);
                AddFlatCurve(DiffSingerUtils.ENE, 2);
            } else {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 92);
                AddFlatCurve(DiffSingerUtils.ENE, 1);
            }
            project.timeAxis.BuildSegments(project);

            var previous = DocManager.Inst.TakeProjectForTest(project);
            DocManager.Inst.SetPhonemizerRunnerForTest(null);
            try {
                // First validation creates OpenUtau's own phonemizer request timestamp.
                // In a GUI process PhonemizerRunner consumes that request asynchronously.
                // This headless proof invokes the exact private core Phonemize implementation
                // synchronously, avoiding any hand-authored phone map or phone timing.
                project.ValidateFull();

                var tsField = typeof(UVoicePart).GetField("notesTimestamp", BindingFlags.Instance | BindingFlags.NonPublic);
                Assert.NotNull(tsField);
                long timestamp = (long)tsField!.GetValue(part)!;
                var noteList = part.notes.ToList();
                var request = new PhonemizerRequest {
                    singer = singer,
                    part = part,
                    timestamp = timestamp,
                    noteIndexes = Enumerable.Range(0, noteList.Count).ToArray(),
                    notes = noteList.Select(n => new[] { n.ToPhonemizerNote(track, part) }).ToArray(),
                    phonemizers = new[] { track.Phonemizer },
                    notePhonemizerIndices = Enumerable.Repeat(0, noteList.Count).ToArray(),
                    timeAxis = project.timeAxis.Clone(),
                };
                var phonemize = typeof(PhonemizerRunner).GetMethod("Phonemize", BindingFlags.Static | BindingFlags.NonPublic);
                Assert.NotNull(phonemize);
                var response = (PhonemizerResponse)phonemize!.Invoke(null, new object[] { request })!;
                part.SetPhonemizerResponse(response);
                project.Validate(new ValidateOptions {
                    SkipTiming = true,
                    Part = part,
                    SkipPhonemizer = true,
                });

                // Optional native OpenUtau phoneme-timing correction. This uses the same
                // per-phoneme offset users edit in OpenUtau; it does not replace the
                // phonemizer or hand-author all phone durations.
                int lOffsetTicks = 0;
                int.TryParse(Environment.GetEnvironmentVariable("GG_VFS_L_OFFSET_TICKS"), out lOffsetTicks);
                if (lOffsetTicks != 0) {
                    var lPhone = part.phonemes.LastOrDefault(p =>
                        string.Equals(p.Parent?.lyric, "говорил", StringComparison.OrdinalIgnoreCase)
                        && (string.Equals(p.phoneme, "ru/l", StringComparison.OrdinalIgnoreCase)
                            || string.Equals(p.rawPhoneme, "ru/l", StringComparison.OrdinalIgnoreCase)));
                    Assert.NotNull(lPhone);
                    var timing = lPhone!.Parent!.GetPhonemeOverride(lPhone.index);
                    timing.offset = -Math.Abs(lOffsetTicks);
                    project.Validate(new ValidateOptions {
                        SkipTiming = true,
                        Part = part,
                        SkipPhonemizer = true,
                    });
                }

                Assert.True(part.PhonemesUpToDate, "Official Russian phonemizer response was not applied.");
                Assert.True(part.phonemes.Count > 0, "Official Russian phonemizer produced no phonemes.");
                var badPhones = part.phonemes.Where(p => p.Error || string.Equals(p.phoneme, "error", StringComparison.OrdinalIgnoreCase)).ToList();
                Assert.True(badPhones.Count == 0,
                    "Invalid official phonemes: " + string.Join(" | ", badPhones.Select(p =>
                        $"{p.phoneme}@{p.position}: {ExceptionChain(p.ErrorException)}")));
                Assert.True(part.renderPhrases.Count > 0,
                    "OpenUtau produced no render phrases despite valid phones: " +
                    string.Join(" ", part.phonemes.Select(p => $"{p.phoneme}@{p.position}")));

                var cancellation = new CancellationTokenSource();
                var rendered = new List<(RenderResult result, string phones)>();
                int generatedPitchGridPoints = 0;
                foreach (var phrase in part.renderPhrases) {
                    Assert.True(((DiffSingerSinger)singer).HasPitchPredictor, "UFR bank exposes no dspitch predictor.");
                    var generatedPitch = renderer.LoadRenderedPitch(phrase, pitchSteps: 12, fastRealtime: false);
                    Assert.NotNull(generatedPitch);
                    generatedPitchGridPoints += ApplyGeneratedPitch(phrase, generatedPitch);
                    ApplyHumanProsody(phrase, variant);
                    ApplySingerPhysics(phrase, variant);
                    Assert.True(generatedPitchGridPoints > 0, "OpenUtau dspitch produced no voiced pitch grid points.");
                    var progress = new Progress(Math.Max(1, phrase.phones.Length));
                    var rr = renderer.Render(phrase, progress, 0, cancellation, true, null).GetAwaiter().GetResult();
                    Assert.NotNull(rr);
                    Assert.NotNull(rr.samples);
                    Assert.True(rr.samples.Length > 4410, "Rendered phrase is implausibly short.");
                    rendered.Add((rr, string.Join(" ", phrase.phones.Select(p => p.phoneme))));
                }

                var dsSinger = singer as DiffSingerSinger;
                var usedVocoder = dsSinger?.getVocoder();
                int sampleRate = dsSinger?.dsConfig.sample_rate ?? 44100;
                double minStartMs = rendered.Min(x => x.result.positionMs - x.result.leadingMs);
                double maxEndMs = rendered.Max(x => (x.result.positionMs - x.result.leadingMs) + x.result.samples.Length * 1000.0 / sampleRate);
                int totalSamples = (int)Math.Ceiling((maxEndMs - minStartMs) * sampleRate / 1000.0) + sampleRate / 2;
                var mix = new float[Math.Max(totalSamples, sampleRate)];
                foreach (var x in rendered) {
                    int start = (int)Math.Round(((x.result.positionMs - x.result.leadingMs) - minStartMs) * sampleRate / 1000.0);
                    for (int i = 0; i < x.result.samples.Length && start + i < mix.Length; i++) {
                        mix[start + i] += x.result.samples[i];
                    }
                }

                float peak = mix.Select(Math.Abs).DefaultIfEmpty(0).Max();
                Assert.True(peak > 0.005f, $"Output nearly silent, peak={peak}");
                if (peak > 0.98f) {
                    float gain = 0.95f / peak;
                    for (int i = 0; i < mix.Length; i++) mix[i] *= gain;
                    peak = 0.95f;
                }

                var tag = Environment.GetEnvironmentVariable("GG_VFS_TAG") ?? "UFR";
                var safeTag = string.Concat(tag.Select(c => char.IsLetterOrDigit(c) || c == '_' || c == '-' ? c : '_'));
                var wav = Path.Combine(outDir!, safeTag + "__OPENUTAU_RU_QC.wav");
                Wave.WriteMono16Wav(wav, mix);
                var manifest = Path.Combine(outDir!, safeTag + "__manifest.txt");
                File.WriteAllText(manifest,
                    $"singer={singer.Name}\n" +
                    $"speaker={chosenSpeaker}\n" +
                    $"variant={variant}\n" +
                    $"l_offset_ticks={lOffsetTicks}\n" +
                    $"render_steps={renderSteps}\n" +
                    $"vocoder_name={usedVocoder?.config?.name ?? "unknown"}\n" +
                    $"vocoder_pitch_controllable={usedVocoder?.pitch_controllable ?? false}\n" +
                    $"singer_id={singer.Id}\n" +
                    $"sample_rate={sampleRate}\n" +
                    $"duration_seconds={mix.Length / (double)sampleRate:F3}\n" +
                    $"peak={peak:F6}\n" +
                    $"phonemizer={track.Phonemizer.Name}\n" +
                    $"lyrics=Я говорил не с ним\n" +
                    $"phrases={rendered.Count}\n" +
                    string.Join("\n", rendered.Select((x, i) => $"phrase_{i+1}_phones={x.phones}")) +
                    $"\ndspitch_predictor=true\ndspitch_steps=12\ngenerated_pitch_grid_points={generatedPitchGridPoints}\n" +
                    "manual_frame_f0=false\nmanual_phoneme_durations=false\nroute=official_ru_phonemizer+openutau_timing+native_dspitch\n");
                Assert.True(File.Exists(wav));
                Assert.True(new FileInfo(wav).Length > 10000);
            } finally {
                DocManager.Inst.SetPhonemizerRunnerForTest(null);
                DocManager.Inst.TakeProjectForTest(previous);
                DocManager.Inst.CommandSink = null;
            }
        }
    }
}