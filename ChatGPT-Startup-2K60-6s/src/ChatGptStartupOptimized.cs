using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

[assembly: AssemblyTitle("ChatGPT Startup Animation")]
[assembly: AssemblyDescription("Upper-left typography and luminous sketch-to-color ChatGPT desktop startup")]
[assembly: AssemblyProduct("ChatGPT Startup Animation")]
[assembly: AssemblyCompany("OpenAI")]
[assembly: AssemblyVersion("1.2.0.0")]
[assembly: AssemblyFileVersion("1.2.0.0")]

namespace ChatGptStartupAnimation
{
    internal static class Program
    {
        private const string AppUserModelId = "OpenAI.Codex_2p2nqsd0c76g0!App";
        internal const string FilmResourceName = "ChatGPTStartup.mp4";
        internal const string PosterResourceName = "ChatGPTPoster.jpg";
        private const string EmbeddedFilmName = "chatgpt-startup-20261020-2k60-6s-v2.mp4";

        [DllImport("user32.dll")]
        private static extern uint GetDpiForSystem();

        [STAThread]
        private static int Main(string[] args)
        {
            Stopwatch startupClock = Stopwatch.StartNew();
            bool preview = HasArgument(args, "--preview") || HasArgument(args, "--preview-test");
            bool previewTest = HasArgument(args, "--preview-test");
            bool acquired;
            using (Mutex mutex = new Mutex(true, @"Local\ChatGptStartupAnimation2K60", out acquired))
            {
                if (!acquired)
                {
                    if (previewTest) WriteError("Another launcher instance is already running.");
                    return 0;
                }

                try
                {
                    Application application = new Application();
                    application.ShutdownMode = ShutdownMode.OnMainWindowClose;
                    FilmSplash window = new FilmSplash(preview, previewTest, startupClock);
                    application.Run(window);
                    return previewTest && !window.PlaybackSucceeded ? 1 : 0;
                }
                catch (Exception error)
                {
                    WriteError(error.ToString());
                    if (!previewTest)
                    {
                        MessageBox.Show(
                            "启动动画无法运行。\n\n" + error.Message,
                            "ChatGPT 启动动画",
                            MessageBoxButton.OK,
                            MessageBoxImage.Error);
                    }
                    return 1;
                }
                finally
                {
                    mutex.ReleaseMutex();
                }
            }
        }

        private static bool HasArgument(string[] args, string expected)
        {
            foreach (string argument in args)
            {
                if (string.Equals(argument, expected, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        internal static double GetSystemDpiScale()
        {
            try
            {
                uint dpi = GetDpiForSystem();
                if (dpi >= 96 && dpi <= 480) return dpi / 96.0;
            }
            catch (EntryPointNotFoundException)
            {
            }
            catch (DllNotFoundException)
            {
            }
            return 1.0;
        }

        internal static string ExtractFilm()
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream resource = assembly.GetManifestResourceStream(FilmResourceName))
            {
                if (resource == null)
                    throw new InvalidOperationException("The embedded startup film is missing.");

                string folder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ChatGPT-Startup-Animation");
                Directory.CreateDirectory(folder);
                string target = Path.Combine(folder, EmbeddedFilmName);
                if (File.Exists(target) && new FileInfo(target).Length == resource.Length)
                    return target;

                string temporary = target + ".tmp";
                using (FileStream output = new FileStream(
                    temporary,
                    FileMode.Create,
                    FileAccess.Write,
                    FileShare.None,
                    1024 * 1024,
                    FileOptions.SequentialScan))
                {
                    resource.CopyTo(output);
                }

                if (File.Exists(target)) File.Delete(target);
                File.Move(temporary, target);
                return target;
            }
        }

        internal static void OpenChatGpt()
        {
            try
            {
                IActivationManager manager = (IActivationManager)new ActivationManager();
                try
                {
                    uint pid;
                    int result = manager.ActivateApplication(AppUserModelId, null, 0, out pid);
                    if (result < 0) Marshal.ThrowExceptionForHR(result);
                    return;
                }
                finally
                {
                    Marshal.ReleaseComObject(manager);
                }
            }
            catch
            {
                Process.Start(new ProcessStartInfo(
                    "explorer.exe",
                    @"shell:AppsFolder\" + AppUserModelId)
                {
                    UseShellExecute = true
                });
            }
        }

        internal static void WriteValidation(string text)
        {
            string folder = Path.Combine(Path.GetTempPath(), "ChatGPT-Startup-Animation");
            Directory.CreateDirectory(folder);
            File.WriteAllText(Path.Combine(folder, "native-preview-validation.txt"), text);
        }

        internal static void WriteError(string text)
        {
            try
            {
                string folder = Path.Combine(Path.GetTempPath(), "ChatGPT-Startup-Animation");
                Directory.CreateDirectory(folder);
                File.WriteAllText(Path.Combine(folder, "launcher-error.txt"), text);
            }
            catch
            {
            }
        }

        [ComImport]
        [Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]
        private class ActivationManager
        {
        }

        [ComImport]
        [Guid("2e941141-7f97-4756-ba1d-9decde894a3d")]
        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IActivationManager
        {
            [PreserveSig]
            int ActivateApplication(
                [MarshalAs(UnmanagedType.LPWStr)] string applicationUserModelId,
                [MarshalAs(UnmanagedType.LPWStr)] string arguments,
                uint options,
                out uint processId);

            [PreserveSig]
            int ActivateForFile(
                [MarshalAs(UnmanagedType.LPWStr)] string applicationUserModelId,
                IntPtr itemArray,
                [MarshalAs(UnmanagedType.LPWStr)] string verb,
                out uint processId);

            [PreserveSig]
            int ActivateForProtocol(
                [MarshalAs(UnmanagedType.LPWStr)] string applicationUserModelId,
                IntPtr itemArray,
                out uint processId);
        }
    }

    internal sealed class FilmSplash : Window
    {
        private readonly bool preview;
        private readonly bool previewTest;
        private readonly Stopwatch startupClock;
        private readonly MediaElement player;
        private readonly Image posterImage;
        private readonly DispatcherTimer watchdog;
        private readonly Stopwatch wallClock = new Stopwatch();
        private readonly Stopwatch playbackClock = new Stopwatch();
        private readonly Task<string> filmTask;
        private bool finished;
        private bool opened;
        private bool cleaned;
        private bool videoVisible;
        private double duration;
        private double lastPosition;
        private double lastProgress;
        private double sourceRequestedAt;
        private double windowReadyMs;
        private double mediaExtractedMs;
        private double mediaOpenedMs;
        private double firstVideoFrameMs;
        private string filmPath = string.Empty;

        internal bool PlaybackSucceeded { get; private set; }

        internal FilmSplash(bool previewOnly, bool onlyValidatePlayback, Stopwatch processClock)
        {
            preview = previewOnly;
            previewTest = onlyValidatePlayback;
            startupClock = processClock;
            Title = "ChatGPT 启动动画";
            WindowStyle = WindowStyle.None;
            ResizeMode = ResizeMode.NoResize;
            AllowsTransparency = false;
            Background = new SolidColorBrush(Color.FromRgb(250, 249, 244));
            Topmost = true;
            ShowInTaskbar = false;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            UseLayoutRounding = true;

            // Keep the window at or below the source's physical pixel size.
            // This avoids an expensive 2K-to-4K upscale on high-DPI Windows 11
            // displays while retaining a crisp 16:9 2K presentation.
            const double designWidth = 2560.0;
            const double designHeight = 1440.0;
            double dpiScale = Program.GetSystemDpiScale();
            double maximumWidth = designWidth / dpiScale;
            double maximumHeight = designHeight / dpiScale;
            double availableWidth = SystemParameters.WorkArea.Width * 0.92;
            double availableHeight = SystemParameters.WorkArea.Height * 0.92;
            Width = Math.Min(maximumWidth, availableWidth);
            Height = Width * designHeight / designWidth;
            if (Height > Math.Min(maximumHeight, availableHeight))
            {
                Height = Math.Min(maximumHeight, availableHeight);
                Width = Height * designWidth / designHeight;
            }

            player = new MediaElement
            {
                LoadedBehavior = MediaState.Manual,
                UnloadedBehavior = MediaState.Manual,
                Stretch = Stretch.Uniform,
                IsMuted = true,
                Volume = 0,
                IsHitTestVisible = false,
                Focusable = false,
                Visibility = Visibility.Visible
            };

            posterImage = new Image
            {
                Stretch = Stretch.Uniform,
                SnapsToDevicePixels = true,
                Source = LoadPoster()
            };
            RenderOptions.SetBitmapScalingMode(posterImage, BitmapScalingMode.HighQuality);

            Grid surface = new Grid
            {
                Background = new SolidColorBrush(Color.FromRgb(250, 249, 244))
            };
            surface.Children.Add(player);
            surface.Children.Add(posterImage);
            Content = surface;

            // Extraction runs in parallel with WPF window creation. The poster
            // is visible immediately, so the user never sees a black first frame.
            filmTask = Task.Run(new Func<string>(Program.ExtractFilm));

            watchdog = new DispatcherTimer(DispatcherPriority.Background);
            watchdog.Interval = TimeSpan.FromMilliseconds(100);
            watchdog.Tick += WatchdogTick;
            player.MediaOpened += MediaOpened;
            player.MediaEnded += MediaEnded;
            player.MediaFailed += MediaFailed;
            PreviewKeyDown += KeyPressed;
            ContentRendered += ContentReady;
            Closed += WindowClosed;
        }

        private static ImageSource LoadPoster()
        {
            using (Stream stream = Assembly.GetExecutingAssembly()
                .GetManifestResourceStream(Program.PosterResourceName))
            {
                if (stream == null)
                    throw new InvalidOperationException("The embedded startup poster is missing.");

                BitmapImage bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.StreamSource = stream;
                bitmap.EndInit();
                bitmap.Freeze();
                return bitmap;
            }
        }

        private void ContentReady(object sender, EventArgs e)
        {
            ContentRendered -= ContentReady;
            windowReadyMs = startupClock.Elapsed.TotalMilliseconds;
            Activate();
            Focus();
            wallClock.Start();
            watchdog.Start();

            filmTask.ContinueWith(
                task =>
                {
                    Dispatcher.BeginInvoke(new Action(delegate
                    {
                        if (finished || cleaned) return;
                        if (task.IsFaulted)
                        {
                            Exception error = task.Exception == null
                                ? null
                                : task.Exception.GetBaseException();
                            Fail("The embedded startup film could not be prepared.", error);
                            return;
                        }
                        BeginMedia(task.Result);
                    }));
                },
                TaskScheduler.Default);
        }

        private void BeginMedia(string path)
        {
            if (finished || cleaned) return;
            mediaExtractedMs = startupClock.Elapsed.TotalMilliseconds;
            filmPath = path;
            sourceRequestedAt = wallClock.Elapsed.TotalSeconds;
            try
            {
                player.Source = new Uri(path, UriKind.Absolute);
                player.Position = TimeSpan.Zero;
                player.Play();
            }
            catch (Exception error)
            {
                Fail("The startup film could not start.", error);
            }
        }

        private void MediaOpened(object sender, RoutedEventArgs e)
        {
            if (finished) return;
            opened = true;
            mediaOpenedMs = startupClock.Elapsed.TotalMilliseconds;
            if (player.NaturalDuration.HasTimeSpan)
                duration = player.NaturalDuration.TimeSpan.TotalSeconds;
            if (duration <= 0 || duration > 30 || double.IsNaN(duration) || double.IsInfinity(duration))
            {
                Fail("The startup film has an invalid duration.", null);
                return;
            }
            lastPosition = player.Position.TotalSeconds;
            lastProgress = wallClock.Elapsed.TotalSeconds;
            playbackClock.Restart();
        }

        private void WatchdogTick(object sender, EventArgs e)
        {
            if (finished) return;
            double elapsed = wallClock.Elapsed.TotalSeconds;
            if (!opened)
            {
                if (sourceRequestedAt > 0 && elapsed - sourceRequestedAt > 8)
                    Fail("The video decoder did not open the startup film.", null);
                return;
            }

            double position = player.Position.TotalSeconds;
            if (position > lastPosition + 0.005)
            {
                lastPosition = position;
                lastProgress = elapsed;
            }
            if (!videoVisible && position >= 0.02)
                RevealVideo();
            if (elapsed - lastProgress > 4)
                Fail("The startup film stopped unexpectedly.", null);
        }

        private void RevealVideo()
        {
            if (videoVisible) return;
            videoVisible = true;
            firstVideoFrameMs = startupClock.Elapsed.TotalMilliseconds;
            DoubleAnimation fade = new DoubleAnimation(1.0, 0.0, TimeSpan.FromMilliseconds(110));
            fade.Completed += delegate
            {
                posterImage.Visibility = Visibility.Collapsed;
            };
            posterImage.BeginAnimation(OpacityProperty, fade);
        }

        private void MediaEnded(object sender, RoutedEventArgs e)
        {
            if (finished) return;
            PlaybackSucceeded = true;
            if (!videoVisible) RevealVideo();
            playbackClock.Stop();
            if (previewTest)
            {
                Program.WriteValidation(
                    "PASS: native MediaElement playback reached MediaEnded.\n" +
                    "App activation was not executed.\n" +
                    "NaturalVideoWidth: " + player.NaturalVideoWidth + "\n" +
                    "NaturalVideoHeight: " + player.NaturalVideoHeight + "\n" +
                    "NaturalDurationSeconds: " +
                    duration.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "PlaybackElapsedSeconds: " +
                    playbackClock.Elapsed.TotalSeconds.ToString(
                        "F6",
                        System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "WindowReadyMs: " + windowReadyMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "MediaExtractedMs: " + mediaExtractedMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "MediaOpenedMs: " + mediaOpenedMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "FirstVideoFrameMs: " + firstVideoFrameMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "WindowSizeDips: " + Width.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) +
                    "x" + Height.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "\n" +
                    "VideoPath: " + filmPath);
            }
            FinishAndOpen();
        }

        private void MediaFailed(object sender, ExceptionRoutedEventArgs e)
        {
            Fail("The startup film could not be decoded by Windows Media Foundation.", e.ErrorException);
        }

        private void KeyPressed(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Escape) return;
            e.Handled = true;
            FinishAndOpen();
        }

        private void FinishAndOpen()
        {
            if (finished) return;
            finished = true;
            StopPlayback();
            if (preview)
            {
                Close();
                return;
            }

            Dispatcher.BeginInvoke(new Action(delegate
            {
                try
                {
                    Program.OpenChatGpt();
                }
                catch (Exception error)
                {
                    Topmost = false;
                    MessageBox.Show(
                        "无法打开桌面版 ChatGPT。请确认 ChatGPT 已安装并至少启动过一次。\n\n" + error.Message,
                        "ChatGPT 启动动画",
                        MessageBoxButton.OK,
                        MessageBoxImage.Error);
                }
                finally
                {
                    Close();
                }
            }), DispatcherPriority.Background);
        }

        private void Fail(string message, Exception error)
        {
            if (finished) return;
            finished = true;
            StopPlayback();
            string details = message + (error == null ? string.Empty : "\n\n" + error.Message);
            Program.WriteError(details + "\n\nVideoPath: " + filmPath);
            Topmost = false;
            if (!previewTest)
            {
                MessageBox.Show(
                    details,
                    "ChatGPT 启动动画",
                    MessageBoxButton.OK,
                    MessageBoxImage.Error);
            }
            Close();
        }

        private void StopPlayback()
        {
            watchdog.Stop();
            wallClock.Stop();
            playbackClock.Stop();
            try
            {
                player.Stop();
            }
            catch
            {
            }
        }

        private void WindowClosed(object sender, EventArgs e)
        {
            if (cleaned) return;
            cleaned = true;
            finished = true;
            StopPlayback();
            watchdog.Tick -= WatchdogTick;
            player.MediaOpened -= MediaOpened;
            player.MediaEnded -= MediaEnded;
            player.MediaFailed -= MediaFailed;
            PreviewKeyDown -= KeyPressed;
            ContentRendered -= ContentReady;
            Closed -= WindowClosed;
            try
            {
                player.Close();
                player.Source = null;
            }
            catch
            {
            }
        }
    }
}
