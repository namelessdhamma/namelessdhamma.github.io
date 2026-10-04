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
            Preferences.Default.DiffSingerSteps = 30;
            Preferences.Default.DiffSingerStepsVariance = 20;
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
                "legato" => 76,
                "clear" => 80,
                "expressive" => 82,
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
            track.Phonemizer = new DiffSingerRussianHhsktPhonemizer();

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
            int[] tones =      { 57,  59,       60,   59,  57 };
            int[] durations = variant switch {
                "legato" =>     new[] { 620, 1260, 560, 220, 1020 },
                "clear" =>      new[] { 580, 1160, 500, 220, 920 },
                "expressive" => new[] { 600, 1240, 540, 240, 1000 },
                _ =>            new[] { 600, 1200, 540, 240, 960 },
            };
            int pos = 0;
            for (int i = 0; i < lyrics.Length; i++) {
                var note = project.CreateNote(tones[i], pos, durations[i]);
                note.lyric = lyrics[i];
                // All performance shaping stays inside OpenUtau's native note/vibrato model.
                if (lyrics[i] is "говорил" or "ним") {
                    if (variant == "legato") {
                        note.vibrato.length = 30;
                        note.vibrato.period = 300;
                        note.vibrato.depth = 10;
                        note.vibrato.@in = 42;
                        note.vibrato.@out = 38;
                    } else if (variant == "expressive") {
                        note.vibrato.length = 46;
                        note.vibrato.period = 235;
                        note.vibrato.depth = 21;
                        note.vibrato.@in = 30;
                        note.vibrato.@out = 28;
                    } else if (variant == "clear") {
                        note.vibrato.length = 32;
                        note.vibrato.period = 280;
                        note.vibrato.depth = 11;
                        note.vibrato.@in = 40;
                        note.vibrato.@out = 35;
                    } else {
                        note.vibrato.length = 38;
                        note.vibrato.period = 260;
                        note.vibrato.depth = 16;
                        note.vibrato.@in = 35;
                        note.vibrato.@out = 30;
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
            if (variant == "legato") {
                AddFlatCurve(DiffSingerUtils.VELC, 114);
                AddFlatCurve(DiffSingerUtils.PEXP, 86);
                AddFlatCurve(DiffSingerUtils.ENE, -3);
            } else if (variant == "clear") {
                AddFlatCurve(DiffSingerUtils.VELC, 124);
                AddFlatCurve(DiffSingerUtils.PEXP, 92);
                AddFlatCurve(DiffSingerUtils.ENE, 1);
            } else if (variant == "expressive") {
                AddFlatCurve(DiffSingerUtils.VELC, 108);
                AddFlatCurve(DiffSingerUtils.PEXP, 100);
                AddFlatCurve(DiffSingerUtils.ENE, 5);
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
                    Assert.True(generatedPitchGridPoints > 0, "OpenUtau dspitch produced no voiced pitch grid points.");
                    var progress = new Progress(Math.Max(1, phrase.phones.Length));
                    var rr = renderer.Render(phrase, progress, 0, cancellation, true, null).GetAwaiter().GetResult();
                    Assert.NotNull(rr);
                    Assert.NotNull(rr.samples);
                    Assert.True(rr.samples.Length > 4410, "Rendered phrase is implausibly short.");
                    rendered.Add((rr, string.Join(" ", phrase.phones.Select(p => p.phoneme))));
                }

                var dsSinger = singer as DiffSingerSinger;
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