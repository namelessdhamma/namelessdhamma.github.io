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
    public class GGNeSNimRebuildATest {
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
            if (!(variant is "human_a" or "human_b" or "human_c" or "song")) return;
            // Performance editing only: native DiffSinger pitch is kept, then a sparse,
            // smooth OpenUtau-style pitch deviation is layered on top.
            float[] xs = { 0f, .10f, .23f, .36f, .50f, .64f, .78f, .90f, 1f };
            float[] ys = variant switch {
                "song" => new float[] { -8, 10, -12, 18, -8, 14, -16, 9, -6 },
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
            if (!(variant is "long_a" or "long_b" or "long_c")) return;
            int level = variant == "long_a" ? 1 : variant == "long_b" ? 2 : 3;
            if (phrase.pitches.Length < 2 || phrase.notes.Length == 0) return;
            float levelScale = level == 1 ? 0.82f : level == 2 ? 1.0f : 1.16f;
            for (int j = 0; j < phrase.pitches.Length; j++) {
                float tick = -phrase.leading + j * 5;
                float delta = 0f;
                for (int i = 1; i < phrase.notes.Length; i++) {
                    var prev = phrase.notes[i - 1];
                    var next = phrase.notes[i];
                    int interval = next.tone - prev.tone;
                    float direction = Math.Sign(interval);
                    int semitones = Math.Abs(interval);
                    if (direction == 0 || semitones == 0) continue;
                    float transition = next.position;
                    float prep = Math.Clamp(4.5f + 2.4f * semitones, 6f, 17f) * levelScale;
                    float over = Math.Clamp(7f + 3.0f * semitones, 10f, 27f) * levelScale;
                    float prepTicks = 28f + 3f * Math.Min(5, semitones);
                    float settleTicks = 58f + 6f * Math.Min(5, semitones);
                    float prepStart = transition - prepTicks;
                    if (tick >= prepStart && tick < transition) {
                        float u = (tick - prepStart) / prepTicks;
                        delta += -direction * prep * (float)Math.Sin(Math.PI * u);
                        if (semitones >= 3 && u > 0.58f) {
                            float v = (u - 0.58f) / 0.42f;
                            v = v * v * (3f - 2f * v);
                            delta += direction * Math.Min(15f, 2.4f * semitones) * levelScale * v;
                        }
                    }
                    float settleEnd = transition + settleTicks;
                    if (tick >= transition && tick <= settleEnd) {
                        float u = (tick - transition) / settleTicks;
                        float damped = (float)(Math.Sin(Math.PI * Math.Min(1.0, u * 1.38)) * Math.Exp(-1.55 * u));
                        delta += direction * over * damped;
                    }
                }
                var note = phrase.notes.FirstOrDefault(n => tick >= n.position && tick <= n.end);
                if (note != null && note.duration > 0) {
                    float u = Math.Clamp((tick - note.position) / note.duration, 0f, 1f);
                    float arch = (float)Math.Sin(Math.PI * u);
                    float semantic = note.lyric switch {
                        "Я" => 1.5f, "говорил" => 5.5f, "не" => 7.5f, "ним" => -3.5f,
                        "тем" => 2.0f, "долго" => 3.0f, "стоял" => 7.0f, "окна" => -1.5f,
                        "ждал" => -5.5f, _ => 0f,
                    };
                    delta += arch * semantic * levelScale;
                }
                phrase.pitches[j] += delta;
            }
        }

        [Fact]
        public void RenderNeSNimRebuildA() {
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
                Name = "UFR — OpenUtau Long Human Vocal",
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
                "rebuild_a" => 108,
                "song_v2" => 108,
                "song" => 108,
                "long_a" => 74,
                "long_b" => 72,
                "long_c" => 70,
                _ => 80,
            }));
            project.timeAxis.BuildSegments(project);
            RegisterBaseExpressions(project);

            var renderer = new DiffSingerRenderer();
            var track = project.tracks[0];
            track.TrackNo = 0;
            track.TrackName = "GG-VFS Long Human Vocal";
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
                name = "GG long human vocal",
                trackNo = 0,
                position = 0,
            };
            project.parts.Add(part);

            // GG "Не с ним" REBUILD A.
            // Clean literary spelling only. Stress is separate score metadata.
            // Word durations and rests are explicitly authored line by line.
            int Bar = 1920;

            int Vowels(string w) => w.Count(c => "аеёиоуыэюяАЕЁИОУЫЭЮЯ".Contains(c));
            int[] SplitWordTicks(int total, int syllables, int stress) {
                if (syllables <= 1) return new[] { total };
                var weights = Enumerable.Range(0, syllables)
                    .Select(i => i == stress ? 1.85 : 1.0)
                    .ToArray();
                double sum = weights.Sum();
                var result = new int[syllables];
                int used = 0;
                for (int i = 0; i < syllables; i++) {
                    if (i == syllables - 1) {
                        result[i] = Math.Max(90, total - used);
                    } else {
                        int d = Math.Max(90, (int)Math.Round((total * weights[i] / sum) / 30.0) * 30);
                        result[i] = d;
                        used += d;
                    }
                }
                int diff = total - result.Sum();
                result[^1] += diff;
                return result;
            }

            int[] FitMotif(int[] motif, int count, int transpose) {
                if (count <= 0) return Array.Empty<int>();
                if (count == 1) return new[] { motif[0] + transpose };
                var result = new int[count];
                for (int i = 0; i < count; i++) {
                    double x = i * (motif.Length - 1.0) / (count - 1.0);
                    int a = Math.Clamp((int)Math.Floor(x), 0, motif.Length - 1);
                    int b = Math.Clamp(a + 1, 0, motif.Length - 1);
                    double u = x - a;
                    result[i] = (int)Math.Round(motif[a] * (1.0 - u) + motif[b] * u) + transpose;
                }
                return result;
            }

            // Stable song motifs. Repetition is intentional songwriting, not per-word pitch cycling.
            int[] VA = {57,57,60,60,59,57,59,60,62,60,59,57,55,57,57,55};
            int[] VB = {57,59,60,62,60,59,57,55,57,60,62,64,62,60,59,57};
            int[] VC = {55,57,59,60,59,57,55,57,60,62,60,59,57,55,52,55};
            int[] CH1 = {64,64,67,69,69,67,64,62,64,67,69,72,71,69,67,64};
            int[] CH2 = {64,67,69,72,72,71,69,67,69,72,74,72,69,67,64,64};
            int[] BR1 = {60,62,64,65,67,69,67,65,64,62,64,67,69,67,64,62};
            int[] BR2 = {62,64,65,67,69,71,72,71,69,67,65,64,62,64,67,69};
            int[] FIN1 = {64,67,69,72,74,72,69,67,69,72,74,76,74,72,69,67};
            int[] FIN2 = {67,69,72,74,76,76,74,72,69,72,74,76,77,76,72,69};
            int[] CODA = {64,64,62,60,59,57,55,57,55,52};

            void AddLine(
                int startBar,
                int pickup,
                string[] words,
                int[] wordTicks,
                int[] restAfter,
                int[] stressSyllables,
                int[] motif,
                int transpose = 0) {
                Assert.True(words.Length == wordTicks.Length);
                Assert.True(words.Length == restAfter.Length);
                Assert.True(words.Length == stressSyllables.Length);

                int totalSyllables = words.Sum(w => Math.Max(1, Vowels(w)));
                var melody = FitMotif(motif, totalSyllables, transpose);
                int mel = 0;
                int p = startBar * Bar + pickup;

                for (int wi = 0; wi < words.Length; wi++) {
                    string word = words[wi];
                    int syllables = Math.Max(1, Vowels(word));
                    int stress = Math.Clamp(stressSyllables[wi], 0, syllables - 1);
                    int[] ds = SplitWordTicks(wordTicks[wi], syllables, stress);

                    for (int si = 0; si < syllables; si++) {
                        int tone = Math.Clamp(melody[mel++], 52, 79);
                        var note = project.CreateNote(tone, p, ds[si]);
                        note.lyric = si == 0 ? word : "+";

                        bool stressed = si == stress;
                        if (stressed && ds[si] >= 390) {
                            note.vibrato.length = 24;
                            note.vibrato.period = 206;
                            note.vibrato.depth = 10;
                            note.vibrato.@in = 68;
                            note.vibrato.@out = 52;
                        }
                        if (wi == words.Length - 1 && si == syllables - 1 && ds[si] >= 540) {
                            note.vibrato.length = 42;
                            note.vibrato.period = 190;
                            note.vibrato.depth = 17;
                            note.vibrato.@in = 58;
                            note.vibrato.@out = 44;
                        }
                        part.notes.Add(note);
                        p += ds[si];
                    }
                    p += restAfter[wi];
                }
            }

            // VERSE I — 3 bars per line. Each line leaves a deliberate instrumental reply window.
            AddLine(8,240,
                new[]{"мы","встретились","с","тобой","как","люди","видятся","во","сне"},
                new[]{240,720,120,510,210,450,660,150,690},
                new[]{30,45,15,210,30,45,45,15,0},
                new[]{0,0,0,1,0,0,0,0,0}, VA);

            AddLine(11,120,
                new[]{"узнали","лица","но","не","смели","прикоснуться"},
                new[]{660,480,180,180,570,1110},
                new[]{45,180,30,30,120,0},
                new[]{1,0,0,0,0,2}, VB);

            AddLine(14,180,
                new[]{"два","голоса","блуждали","в","тишине"},
                new[]{210,690,780,120,990},
                new[]{30,150,90,30,0},
                new[]{0,0,1,0,2}, VC);

            AddLine(17,120,
                new[]{"как","две","тропы","которым","не","сомкнуться"},
                new[]{180,180,570,690,180,1080},
                new[]{30,30,150,75,45,0},
                new[]{0,0,1,1,0,1}, VB);

            AddLine(20,180,
                new[]{"вино","нагрелось","память","стёрлась","в","пыль"},
                new[]{510,690,510,660,120,720},
                new[]{45,150,45,90,30,0},
                new[]{1,1,0,0,0,0}, VA, 0);

            AddLine(23,120,
                new[]{"как","в","книге","что","давно","не","открывали"},
                new[]{180,120,480,180,510,180,1020},
                new[]{30,15,150,30,60,30,0},
                new[]{0,0,0,0,1,0,2}, VB, 2);

            AddLine(26,180,
                new[]{"смеялись","мы","но","каждый","позабыл"},
                new[]{720,210,180,570,960},
                new[]{60,150,30,90,0},
                new[]{1,0,0,0,2}, VA);

            AddLine(29,120,
                new[]{"это","не","тот","кого","мы","вспоминали"},
                new[]{420,180,330,480,180,1110},
                new[]{45,30,210,60,45,0},
                new[]{0,0,0,1,0,2}, VC, 2);

            // CHORUS — 2 bars per line, same melodic identity on both occurrences.
            void Chorus(int bar) {
                AddLine(bar,120,
                    new[]{"я","говорил","не","с","ним"},
                    new[]{210,810,180,120,870},
                    new[]{30,90,30,15,0},
                    new[]{0,2,0,0,0}, CH1);
                AddLine(bar+2,60,
                    new[]{"я","говорил","с","собой"},
                    new[]{210,810,120,930},
                    new[]{30,90,30,0},
                    new[]{0,2,0,1}, CH1, 2);
                AddLine(bar+4,120,
                    new[]{"а","он","в","моих","словах"},
                    new[]{150,270,120,660,900},
                    new[]{30,60,30,90,0},
                    new[]{0,0,0,1,1}, CH2);
                AddLine(bar+6,60,
                    new[]{"искал","лишь","голос","свой"},
                    new[]{600,240,660,1050},
                    new[]{60,60,90,0},
                    new[]{1,0,0,0}, CH2, 2);
            }
            Chorus(32);

            // VERSE II
            AddLine(44,180,
                new[]{"за","стол","подсел","незримый","третий","гость"},
                new[]{180,300,570,750,600,720},
                new[]{30,60,120,60,90,0},
                new[]{0,0,1,1,0,0}, VA);

            AddLine(47,120,
                new[]{"тот","кем","мы","были","прежде","до","разлуки"},
                new[]{300,240,180,450,510,180,990},
                new[]{30,30,30,60,150,30,0},
                new[]{0,0,0,0,0,0,1}, VB);

            AddLine(50,180,
                new[]{"он","знал","наперечёт","и","смех","и","злость"},
                new[]{210,330,1050,120,390,120,720},
                new[]{45,60,180,30,60,30,0},
                new[]{0,0,3,0,0,0,0}, VC, 2);

            AddLine(53,120,
                new[]{"и","не","давал","пожать","друг","другу","руки"},
                new[]{150,180,570,600,300,480,780},
                new[]{30,30,90,150,45,60,0},
                new[]{0,0,1,1,0,0,0}, VB);

            Chorus(56);

            // BRIDGE — longer rhetorical spaces inside the line.
            AddLine(64,180,
                new[]{"взирали","сквозь","друг","друга","в","давний","год"},
                new[]{690,300,300,480,120,570,780},
                new[]{60,45,30,300,30,90,0},
                new[]{1,0,0,0,0,0,0}, BR1);

            AddLine(67,120,
                new[]{"который","общим","был","и","незабвенным"},
                new[]{690,570,270,120,1170},
                new[]{60,150,45,30,0},
                new[]{1,0,0,0,2}, BR2);

            AddLine(70,180,
                new[]{"а","прошлое","смыкало","тёмный","грот"},
                new[]{150,750,720,600,930},
                new[]{30,120,180,90,0},
                new[]{0,0,1,0,0}, BR1, 2);

            AddLine(73,120,
                new[]{"былого","что","осталось","неизменным"},
                new[]{690,180,780,1260},
                new[]{120,180,120,0},
                new[]{1,0,1,2}, BR2, 2);

            // FINAL — highest register and longest structural endings.
            AddLine(88,180,
                new[]{"не","память","виновата","ведь","она"},
                new[]{180,570,960,210,900},
                new[]{30,120,180,60,0},
                new[]{0,0,2,0,1}, FIN1);

            AddLine(91,120,
                new[]{"сумела","нас","свести","в","житейском","круге"},
                new[]{660,240,600,120,780,870},
                new[]{60,60,150,30,90,0},
                new[]{1,0,1,0,1,0}, FIN1, 2);

            AddLine(94,180,
                new[]{"ошибка","этой","встречи","лишь","одна"},
                new[]{660,510,570,240,990},
                new[]{60,120,180,60,0},
                new[]{0,0,0,0,1}, FIN2);

            AddLine(97,120,
                new[]{"смотрели","в","прошлое","а","вовсе","не","друг","в","друга"},
                new[]{690,120,720,150,510,180,300,120,900},
                new[]{45,30,240,30,90,30,45,30,0},
                new[]{1,0,0,0,0,0,0,0,0}, FIN2);

            // CODA — reduced, descending, exposed.
            AddLine(100,360,
                new[]{"того","кто","был","напротив"},
                new[]{540,240,300,1110},
                new[]{90,90,180,0},
                new[]{1,0,0,1}, CODA);

            AddLine(103,480,
                new[]{"я","так","и","не","увидел"},
                new[]{210,300,150,180,1350},
                new[]{60,90,45,60,0},
                new[]{0,0,0,0,1}, CODA, -2);

            part.Duration = 110 * Bar;

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
            if (variant == "long_a" || variant == "long_b" || variant == "long_c") {
                int level = variant == "long_a" ? 1 : variant == "long_b" ? 2 : 3;
                AddFlatCurve(DiffSingerUtils.VELC, level == 1 ? 121 : level == 2 ? 120 : 119);
                var pn = part.notes.ToList();
                Assert.True(pn.Count == 15, "Long human profile expects 15 lexical notes.");
                int[] X(params int[] indices) => indices.Select(i => pn[i].position).ToArray();
                int[] Scale(int[] values, float scale) => values.Select(v => (int)Math.Round(v * scale)).ToArray();
                float dynScale = level == 1 ? 0.82f : level == 2 ? 1.0f : 1.14f;
                float varScale = level == 1 ? 0.86f : level == 2 ? 1.0f : 1.10f;
                int[] arcX = X(0,1,2,4,5,7,9,10,12,14);
                AddShapeCurve(Ustx.DYN, arcX,
                    Scale(new[] { -10, -4, 7, -6, -12, -5, 1, 11, -1, -15 }, dynScale));
                AddShapeCurve(DiffSingerUtils.ENE, arcX,
                    Scale(new[] { -7, -3, 4, -5, -9, -4, 0, 6, -3, -10 }, varScale));
                AddShapeCurve(Ustx.TENC, arcX,
                    Scale(new[] { -11, -6, 3, -8, -13, -7, -2, 6, -6, -14 }, varScale));
                AddShapeCurve(Ustx.BREC, arcX,
                    Scale(new[] { 9, 6, 3, 7, 10, 7, 5, 3, 7, 12 }, varScale));
                AddShapeCurve(Ustx.VOIC, arcX,
                    new[] { 97, 99, 100, 98, 96, 98, 99, 100, 98, 95 });
                AddShapeCurve(DiffSingerUtils.PEXP, arcX,
                    new[] { 82, 91, 99, 86, 78, 88, 94, 100, 86, 75 });
            } else if (variant == "rebuild_a") {
                int bar = 1920;
                AddFlatCurve(DiffSingerUtils.VELC, 120);
                AddShapeCurve(Ustx.DYN,
                    new[] {0,8*bar,32*bar,40*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,106*bar,110*bar},
                    new[] {-28,-12,6,-10,-8,8,1,4,13,-9,-16,-26});
                AddShapeCurve(DiffSingerUtils.ENE,
                    new[] {0,8*bar,32*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,110*bar},
                    new[] {-14,-8,2,-5,4,0,5,9,-7,-14});
                AddShapeCurve(Ustx.TENC,
                    new[] {0,8*bar,32*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,110*bar},
                    new[] {-28,-17,-4,-13,-2,-8,1,8,-16,-30});
                AddShapeCurve(Ustx.BREC,
                    new[] {0,8*bar,32*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,110*bar},
                    new[] {14,10,6,9,5,8,5,4,11,16});
                AddShapeCurve(Ustx.VOIC,
                    new[] {0,8*bar,32*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,110*bar},
                    new[] {94,97,100,98,100,99,100,100,97,93});
                AddShapeCurve(DiffSingerUtils.PEXP,
                    new[] {0,8*bar,32*bar,44*bar,56*bar,64*bar,76*bar,88*bar,100*bar,110*bar},
                    new[] {72,84,100,86,100,92,97,100,80,70});
            } else             if (variant == "singer_a" || variant == "singer_b" || variant == "singer_c") {
                int level = variant == "singer_a" ? 1 : variant == "singer_b" ? 2 : 3;
                AddFlatCurve(DiffSingerUtils.VELC, level == 1 ? 121 : level == 2 ? 120 : 119);

                // Macro phrase arc: enter quietly, build through "говорил",
                // crest on "не", then relax through "с ним".
                var performanceNotes = part.notes.ToList();
                Assert.True(performanceNotes.Count == 5, "Singer profile expects the five-word QC phrase.");
                var n0 = performanceNotes[0]; var n1 = performanceNotes[1]; var n2 = performanceNotes[2];
                var n3 = performanceNotes[3]; var n4 = performanceNotes[4];
                AddShapeCurve(Ustx.DYN,
                    new[] { n0.position, n0.position + n0.duration/2, n1.position,
                            n1.position + n1.duration/2, n2.position, n2.position + n2.duration/2,
                            n3.position, n4.position, n4.position + n4.duration/2, n4.End, part.Duration },
                    level == 1 ? new[] { -22, -10, -9, 4, 6, 12, -3, -8, -2, -18, -26 } :
                    level == 2 ? new[] { -26, -12, -10, 6, 8, 16, -4, -10, 0, -21, -30 } :
                                 new[] { -30, -14, -12, 8, 10, 20, -5, -12, 2, -24, -34 });
                AddShapeCurve(DiffSingerUtils.ENE,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n2.position + n2.duration/2, n3.position,
                            n4.position, n4.position + n4.duration/2, n4.End, part.Duration },
                    level == 1 ? new[] { -12, -8, -2, 0, 5, -5, -10, -5, -15, -18 } :
                    level == 2 ? new[] { -14, -9, 0, 2, 8, -6, -12, -5, -17, -20 } :
                                 new[] { -16, -10, 2, 4, 10, -7, -14, -4, -19, -22 });
                AddShapeCurve(DiffSingerUtils.PEXP,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.End, part.Duration },
                    level == 1 ? new[] { 80, 88, 96, 100, 86, 91, 76, 72 } :
                    level == 2 ? new[] { 78, 90, 100, 100, 84, 94, 74, 70 } :
                                 new[] { 76, 92, 100, 100, 82, 96, 72, 68 });
                AddShapeCurve(Ustx.TENC,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.End, part.Duration },
                    level == 1 ? new[] { -26, -24, -20, -18, -24, -26, -30, -32 } :
                    level == 2 ? new[] { -34, -26, -12, -5, -25, -30, -39, -41 } :
                                 new[] { -38, -28, -10, -2, -26, -32, -42, -44 });
                AddShapeCurve(Ustx.BREC,
                    new[] { n0.position, n1.position, n1.position + n1.duration/2,
                            n2.position, n3.position, n4.position, n4.position + n4.duration/2, n4.End, part.Duration },
                    level == 1 ? new[] { 14, 12, 10, 9, 11, 12, 14, 17, 18 } :
                    level == 2 ? new[] { 18, 13, 7, 4, 12, 13, 17, 23, 26 } :
                                 new[] { 20, 14, 6, 3, 13, 14, 19, 25, 28 });
                AddShapeCurve(Ustx.VOIC,
                    new[] { n0.position, n1.position, n2.position, n3.position, n4.position, n4.End, part.Duration },
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
                // Headless equivalent of OpenUtau's normal extender grouping:
                // a lexical leading note plus following + / +~ notes must be sent
                // to the phonemizer as one note group, not as independent lyrics.
                var phonemizerGroups = new List<Phonemizer.Note[]>();
                var phonemizerGroupIndexes = new List<int>();
                for (int ni = 0; ni < noteList.Count; ni++) {
                    var pn = noteList[ni].ToPhonemizerNote(track, part);
                    bool extender = noteList[ni].lyric.StartsWith("+", StringComparison.Ordinal);
                    if (extender && phonemizerGroups.Count > 0) {
                        var expanded = phonemizerGroups[^1].ToList();
                        expanded.Add(pn);
                        phonemizerGroups[^1] = expanded.ToArray();
                    } else {
                        phonemizerGroups.Add(new[] { pn });
                        phonemizerGroupIndexes.Add(ni);
                    }
                }
                var request = new PhonemizerRequest {
                    singer = singer,
                    part = part,
                    timestamp = timestamp,
                    noteIndexes = phonemizerGroupIndexes.ToArray(),
                    notes = phonemizerGroups.ToArray(),
                    phonemizers = new[] { track.Phonemizer },
                    notePhonemizerIndices = Enumerable.Repeat(0, phonemizerGroups.Count).ToArray(),
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
                        && ((p.phoneme?.EndsWith("/l", StringComparison.OrdinalIgnoreCase) ?? false)
                            || (p.rawPhoneme?.EndsWith("/l", StringComparison.OrdinalIgnoreCase) ?? false)
                            || string.Equals(p.phoneme, "l", StringComparison.OrdinalIgnoreCase)
                            || string.Equals(p.rawPhoneme, "l", StringComparison.OrdinalIgnoreCase)));
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
                double minStartMs = 0.0;
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
                    $"lyrics=Не с ним — full song phonetic layer\n" +
                    $"phrases={rendered.Count}\n" +
                    string.Join("\n", rendered.Select((x, i) => $"phrase_{i+1}_phones={x.phones}")) +
                    "\n" +
                    string.Join("\n", part.phonemes.Select((p, i) =>
                        $"phone_{i+1}=lyric:{p.Parent?.lyric}|idx:{p.index}|phone:{p.phoneme}|raw:{p.rawPhoneme}|pos:{p.position}|dur:{p.Duration}|pos_ms:{p.PositionMs:F2}|dur_ms:{p.DurationMs:F2}|pre:{p.preutter:F2}|ovl:{p.overlap:F2}|adj:{p.adjacent}|overlapped:{p.overlapped}")) +
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