// morphbench.exe - окно запуска: поднять сервер, остановить, состояние, папка обзора, страница.
//
// Зачем оно нужно. MO2 подменяет файловую систему только тем процессам, которые запустил
// сам (и их потомкам): моды сливаются в один Data игры библиотекой usvfs. Чтобы верстак
// увидел меши всей сборки, его надо запустить из MO2 - а MO2 запускает исполняемые файлы,
// не скрипты. Это окно и есть такой исполняемый файл: запущенное из MO2, оно поднимает
// `python mb.py serve` своим потомком, и тот видит Data со всеми модами.
//
// Окно ничего не считает и ничего не знает о мешах. Всё, что оно умеет, - вызовы того же
// сервера, что и командная строка: `serve --status`, `serve`, `serve --stop`, `/api/root`,
// открыть страницу. Ни одного пути внутри: модуль - рядом с exe (там лежит mb.py), либо
// папка доводом, либо переменная MORPHBENCH_HOME; Python - переменная MORPHBENCH_PYTHON,
// ключ "python" в morphbench.json, python.exe по PATH (кроме заглушки магазина Windows),
// реестр PythonCore, либо запускатель py.exe.
//
// Доводы: --start - поднять сервер и открыть страницу сразу; --root <папка> - корень обзора
// на этот запуск; <папка> - где лежит mb.py.
//
// Сборка - штатным компилятором .NET Framework, который есть на любой Windows:
//     launcher\build.cmd
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var options = Options.Parse(args);
        if (options.Diag)
        {
            // Диагностика без окна: что python видит из-под MO2 - в файл рядом с exe.
            // Так проверяют VFS без человека у экрана: запуск через MO2, ответ - в файле.
            string home = Module.FindHome(options.Home);
            string python = home == null ? null : Module.FindPython(home);
            string text = home == null ? "нет mb.py" : python == null ? "нет python"
                : new Launcher(home, python).Cli("env --json") + "\n---catalog---\n"
                  + new Launcher(home, python).Cli("render --entry assets/malebodywerewolf_0.nif --size 300x300 --colliders --out morphbench.diag.png --json");
            File.WriteAllText(Path.Combine(home ?? AppDomain.CurrentDomain.BaseDirectory, "morphbench.diag.json"),
                              text, new UTF8Encoding(false));
            return;
        }
        Application.Run(new MainForm(options));
    }
}

// ---- доводы командной строки ----------------------------------------------------------------
class Options
{
    public string Home;          // папка с mb.py, если названа доводом
    public string Root;          // корень обзора на этот запуск
    public bool Start;           // поднять сервер сразу
    public bool Diag;            // без окна: env --json в файл и выйти

    public static Options Parse(string[] args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if (a == "--start") o.Start = true;
            else if (a == "--diag") o.Diag = true;
            else if (a == "--root" && i + 1 < args.Length) o.Root = args[++i];
            else if (a.StartsWith("--root=")) o.Root = a.Substring(7);
            else if (!a.StartsWith("--")) o.Home = a;
        }
        return o;
    }
}

// ---- где модуль и где Python -------------------------------------------------------------
static class Module
{
    public const string Script = "mb.py";

    public static string FindHome(string named)
    {
        var candidates = new List<string>();
        if (!string.IsNullOrEmpty(named)) candidates.Add(named);
        string env = Environment.GetEnvironmentVariable("MORPHBENCH_HOME");
        if (!string.IsNullOrEmpty(env)) candidates.Add(env);
        candidates.Add(AppDomain.CurrentDomain.BaseDirectory);
        candidates.Add(Directory.GetCurrentDirectory());
        foreach (string dir in candidates)
        {
            try
            {
                string full = Path.GetFullPath(dir);
                if (File.Exists(Path.Combine(full, Script))) return full;
            }
            catch (Exception) { }
        }
        return null;
    }

    public static string FindPython(string home)
    {
        string env = Environment.GetEnvironmentVariable("MORPHBENCH_PYTHON");
        if (IsFile(env)) return env;
        string fromConfig = PythonFromConfig(Path.Combine(home, "morphbench.json"));
        if (IsFile(fromConfig)) return fromConfig;
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string dir in path.Split(Path.PathSeparator))
        {
            if (dir.Trim().Length == 0) continue;
            // Заглушка магазина Windows лежит в WindowsApps: без настоящего Python она
            // открывает магазин вместо того, чтобы что-то запустить.
            if (dir.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0) continue;
            string exe = Path.Combine(dir.Trim(), "python.exe");
            if (IsFile(exe)) return exe;
        }
        string fromRegistry = PythonFromRegistry();
        if (fromRegistry != null) return fromRegistry;
        string launcher = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "py.exe");
        if (IsFile(launcher)) return launcher;
        return null;
    }

    static string PythonFromConfig(string json)
    {
        if (!IsFile(json)) return null;
        try
        {
            // Настройки читает сам верстак; здесь нужен один ключ. Путь в двойных кавычках,
            // косые в нём экранированы - Regex.Unescape их возвращает.
            var m = Regex.Match(File.ReadAllText(json), "\"python\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            return m.Success ? Regex.Unescape(m.Groups[1].Value) : null;
        }
        catch (Exception) { return null; }
    }

    static string PythonFromRegistry()
    {
        foreach (RegistryKey hive in new[] { Registry.CurrentUser, Registry.LocalMachine })
        {
            try
            {
                using (RegistryKey core = hive.OpenSubKey(@"Software\Python\PythonCore"))
                {
                    if (core == null) continue;
                    string[] versions = core.GetSubKeyNames();
                    Array.Sort(versions, StringComparer.OrdinalIgnoreCase);
                    Array.Reverse(versions);           // сначала самая новая
                    foreach (string v in versions)
                    {
                        using (RegistryKey k = core.OpenSubKey(v + @"\InstallPath"))
                        {
                            if (k == null) continue;
                            string exe = k.GetValue("ExecutablePath") as string;
                            if (IsFile(exe)) return exe;
                            string dir = k.GetValue("") as string;
                            if (dir != null && IsFile(Path.Combine(dir, "python.exe")))
                                return Path.Combine(dir, "python.exe");
                        }
                    }
                }
            }
            catch (Exception) { }
        }
        return null;
    }

    public static bool IsFile(string path)
    {
        try { return !string.IsNullOrEmpty(path) && File.Exists(path); }
        catch (Exception) { return false; }
    }

    public static string Quote(string s)
    {
        return "\"" + s.Replace("\"", "\\\"") + "\"";
    }
}

// ---- что окно помнит между запусками -------------------------------------------------------
class Remembered
{
    readonly string path;
    public string Root = "";

    public Remembered(string home)
    {
        path = Path.Combine(home, "morphbench.launcher.json");
        try
        {
            if (File.Exists(path))
            {
                var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
                object r;
                if (d != null && d.TryGetValue("root", out r) && r != null) Root = r.ToString();
            }
        }
        catch (Exception) { }
    }

    public void Save()
    {
        try
        {
            var d = new Dictionary<string, object> { { "root", Root ?? "" } };
            File.WriteAllText(path, new JavaScriptSerializer().Serialize(d), new UTF8Encoding(false));
        }
        catch (Exception) { }
    }
}

// ---- состояние сервера, как его видит окно --------------------------------------------------
class ServerStatus
{
    public string State = "free";          // free, ours, busy - как у ServerLink
    public string Url = "";
    public bool? InsideMo2;                // сервер под MO2?
    public string Root;                    // корень сервера
    public int? Meshes;                    // мешей под корнем
    public bool HereInsideMo2;             // этот процесс под MO2?
    public string HereDataRoot;            // Data игры, которую он видит
    public string Error;                   // почему не удалось спросить

    public bool Up { get { return State == "ours"; } }
}

// ---- клиент сервера: те же вызовы, что у командной строки ----------------------------------
class Launcher
{
    public readonly string Home;
    public readonly string Python;
    public string Url = "";
    public Action<string> Log = delegate { };
    readonly JavaScriptSerializer js = new JavaScriptSerializer();
    Process owned;                          // сервер, поднятый этим окном

    public Launcher(string home, string python)
    {
        Home = home;
        Python = python;
    }

    public bool Owns { get { return owned != null && !owned.HasExited; } }

    // -- командная строка верстака: единственный источник адреса и окружения --
    public ServerStatus StatusFromCli()
    {
        var st = new ServerStatus();
        string outp = RunCli("serve --status --json");
        Log(outp.Trim());                      // что верстак знает об окружении - целиком
        try
        {
            var d = js.Deserialize<Dictionary<string, object>>(FirstJson(outp));
            st.State = Str(d, "state") ?? "free";
            st.Url = Str(d, "url") ?? "";
            st.InsideMo2 = Bool(d, "insideMo2");
            st.Root = Str(d, "root");
            st.Meshes = Int(d, "meshes");
            st.HereInsideMo2 = Bool(d, "hereInsideMo2") ?? false;
            st.HereDataRoot = Str(d, "hereDataRoot");
            Url = st.Url;
        }
        catch (Exception e)
        {
            st.Error = "serve --status не ответил: " + e.Message + "\r\n" + outp.Trim();
        }
        return st;
    }

    public string Cli(string args) { return RunCli(args); }

    // Сервер уже поднят: не поднимать второго, а отдать ему корень обзора. Делается это
    // тем же вызовом `mb.py serve`, что и подъём: правило «свободно - поднять, поднят -
    // подключиться и передать путь» живёт в команде, в одном месте, и своей ветки решения
    // у окна нет. Из-под MO2 передаётся Data игры, которую этот процесс видит сквозь usvfs.
    public string HandOver(string root)
    {
        string args = "serve --no-browser";
        if (!string.IsNullOrEmpty(root)) args += " --root " + Module.Quote(root);
        return RunCli(args);
    }

    string RunCli(string args)
    {
        var start = new ProcessStartInfo(Python, Module.Quote(Path.Combine(Home, Module.Script)) + " " + args)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Home,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        using (var p = Process.Start(start))
        {
            // Две трубы читаются одновременно: если читать их по очереди, потомок, забивший
            // вторую трубу (длинная трассировка), встанет на записи, и первая никогда
            // не закроется - окно зависло бы ровно тогда, когда нужна диагностика.
            var err = p.StandardError.ReadToEndAsync();
            string o = p.StandardOutput.ReadToEnd();
            p.WaitForExit();
            return o + err.Result;
        }
    }

    // -- сервер по HTTP: то же, что делает ServerLink --
    public ServerStatus Probe(ServerStatus previous)
    {
        var st = new ServerStatus
        {
            Url = Url, HereInsideMo2 = previous.HereInsideMo2, HereDataRoot = previous.HereDataRoot,
        };
        if (string.IsNullOrEmpty(Url)) { st.State = "free"; return st; }
        try
        {
            var env = Get("api/environment");
            st.State = "ours";
            st.InsideMo2 = Bool(env, "insideMo2");
            st.Root = Str(env, "root");
            try
            {
                var root = Get("api/root");
                st.Root = Str(root, "root");
                st.Meshes = Int(root, "meshes");
            }
            catch (Exception) { }
        }
        catch (WebException e)
        {
            // Соединение есть, ответа нет - это не чужая программа, а неизвестно кто:
            // чаще всего наш сервер под замком на обходе большой папки.
            st.State = e.Status == WebExceptionStatus.ConnectFailure ? "free"
                : e.Status == WebExceptionStatus.Timeout ? "slow" : "busy";
            if (st.State != "free") st.Error = e.Message;
        }
        catch (Exception e)
        {
            st.State = "busy";
            st.Error = e.Message;
        }
        return st;
    }

    public Dictionary<string, object> SetRoot(string root)
    {
        return Get("api/root?root=" + Uri.EscapeDataString(root));
    }

    public void Start(string root)
    {
        if (Owns) return;
        string args = Module.Quote(Path.Combine(Home, Module.Script)) + " serve --no-browser --json";
        // Сервер уходит вместе с этим окном САМ. Мирное закрытие останавливает его и так,
        // но снятое жёстко окно на это времени не имеет, и без сторожа оставался бы
        // невидимый сервер: порт занят, подмена MO2 для него устарела, а следующий запуск
        // молча подключился бы именно к нему.
        args += " --parent " + Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture);
        if (!string.IsNullOrEmpty(root)) args += " --root " + Module.Quote(root);
        var start = new ProcessStartInfo(Python, args)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Home,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        Log("> " + Python + " " + args);
        owned = Process.Start(start);
        owned.EnableRaisingEvents = true;
        owned.OutputDataReceived += (s, e) => { if (e.Data != null) Log(e.Data); };
        owned.ErrorDataReceived += (s, e) => { if (e.Data != null) Log(e.Data); };
        owned.Exited += (s, e) => Log("сервер завершился, код " + SafeExitCode(owned));
        owned.BeginOutputReadLine();
        owned.BeginErrorReadLine();
    }

    static string SafeExitCode(Process p)
    {
        try { return p.ExitCode.ToString(); } catch (Exception) { return "?"; }
    }

    public void Stop()
    {
        try
        {
            Get("api/shutdown");
        }
        catch (Exception e)
        {
            Log("остановка: " + e.Message);
        }
        var p = owned;
        if (p == null) return;
        if (!p.WaitForExit(5000))
        {
            Log("сервер не вышел за 5 с - снимаю");
            try { p.Kill(); } catch (Exception) { }
        }
        owned = null;
    }

    public void OpenPage()
    {
        if (string.IsNullOrEmpty(Url)) return;
        Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
    }

    Dictionary<string, object> Get(string path)
    {
        var req = (HttpWebRequest)WebRequest.Create(Url + path);
        req.Timeout = 30000;                   // обход большой папки может длиться секунды
        req.Proxy = null;                      // адрес местный, прокси из окружения ни к чему
        try
        {
            using (var resp = (HttpWebResponse)req.GetResponse())
            {
                string server = resp.Headers["Server"] ?? "";
                if (!server.StartsWith("morphbench/")) throw new Exception("на " + Url + " отвечает не morphbench");
                return js.Deserialize<Dictionary<string, object>>(ReadAll(resp));
            }
        }
        catch (WebException e)
        {
            var resp = e.Response as HttpWebResponse;
            if (resp == null) throw;
            // Отказ сервера - его словами: {"error": ...}
            string text = ReadAll(resp);
            string message = text;
            try
            {
                var d = js.Deserialize<Dictionary<string, object>>(text);
                object err;
                if (d != null && d.TryGetValue("error", out err) && err != null) message = err.ToString();
            }
            catch (Exception) { }
            throw new Exception(message);
        }
    }

    static string ReadAll(HttpWebResponse resp)
    {
        using (var r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) return r.ReadToEnd();
    }

    static string FirstJson(string text)
    {
        int i = text.IndexOf('{');
        int j = text.LastIndexOf('}');
        if (i < 0 || j < i) throw new Exception("в ответе нет JSON");
        return text.Substring(i, j - i + 1);
    }

    static string Str(Dictionary<string, object> d, string key)
    {
        object v;
        return d != null && d.TryGetValue(key, out v) && v != null ? v.ToString() : null;
    }

    static bool? Bool(Dictionary<string, object> d, string key)
    {
        object v;
        if (d == null || !d.TryGetValue(key, out v) || v == null) return null;
        return v is bool ? (bool)v : (bool?)null;
    }

    static int? Int(Dictionary<string, object> d, string key)
    {
        object v;
        if (d == null || !d.TryGetValue(key, out v) || v == null) return null;
        try { return Convert.ToInt32(v); } catch (Exception) { return null; }
    }
}

// ---- окно -----------------------------------------------------------------------------------
class MainForm : Form
{
    readonly Options options;
    Launcher launcher;
    Remembered remembered;
    ServerStatus status = new ServerStatus();
    bool probing;
    bool warnedForeign;                     // предупреждение о сервере вне MO2 - один раз
    int waitTicks;                          // сколько секунд ещё ждать подъёма своего сервера

    readonly Label stateLabel = new Label();
    readonly Label envLabel = new Label();
    readonly TextBox rootBox = new TextBox();
    readonly Button browseButton = new Button();
    readonly Button applyButton = new Button();
    readonly Button startButton = new Button();
    readonly Button stopButton = new Button();
    readonly Button pageButton = new Button();
    readonly Button refreshButton = new Button();
    readonly TextBox logBox = new TextBox();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();

    public MainForm(Options options)
    {
        this.options = options;
        Text = "morphbench";
        Font = new Font("Segoe UI", 9f);
        // Размеры заданы для 96 dpi и умножаются на масштаб экрана сами: шрифты и кнопки
        // WinForms масштабирует по dpi, а размер окна - нет.
        AutoScaleMode = AutoScaleMode.None;
        float k;
        using (var g = CreateGraphics()) k = g.DpiX / 96f;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size((int)(680 * k), (int)(420 * k));
        MinimumSize = new Size((int)(560 * k), (int)(320 * k));
        Build();
        Load += OnLoad;
        FormClosing += OnClosing;
    }

    void Build()
    {
        var grid = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(10), ColumnCount = 1 };
        grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        grid.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));

        stateLabel.AutoSize = true;
        stateLabel.Font = new Font(Font, FontStyle.Bold);
        stateLabel.Margin = new Padding(0, 0, 0, 2);
        envLabel.AutoSize = true;
        envLabel.ForeColor = SystemColors.GrayText;
        envLabel.Margin = new Padding(0, 0, 0, 8);
        // Длинный корень не должен раздвигать окно: подписи переносятся по его ширине.
        grid.SizeChanged += (s, e) =>
        {
            int w = Math.Max(100, grid.ClientSize.Width - grid.Padding.Horizontal);
            stateLabel.MaximumSize = new Size(w, 0);
            envLabel.MaximumSize = new Size(w, 0);
        };

        var rootRow = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 4, Margin = new Padding(0, 0, 0, 8) };
        rootRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        rootRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        rootRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        rootRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        var rootLabel = new Label { Text = "Корень обзора:", AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 6, 6, 0) };
        rootBox.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        browseButton.Text = "…";
        browseButton.AutoSize = true;
        browseButton.Click += (s, e) => Browse();
        applyButton.Text = "Применить";
        applyButton.AutoSize = true;
        applyButton.Click += (s, e) => Apply();
        rootRow.Controls.Add(rootLabel, 0, 0);
        rootRow.Controls.Add(rootBox, 1, 0);
        rootRow.Controls.Add(browseButton, 2, 0);
        rootRow.Controls.Add(applyButton, 3, 0);

        var buttons = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Margin = new Padding(0, 0, 0, 8) };
        startButton.Text = "Поднять сервер";
        stopButton.Text = "Остановить";
        pageButton.Text = "Открыть страницу";
        refreshButton.Text = "Обновить";
        foreach (var b in new[] { startButton, stopButton, pageButton, refreshButton })
        {
            b.AutoSize = true;
            b.Padding = new Padding(6, 2, 6, 2);
            buttons.Controls.Add(b);
        }
        startButton.Click += (s, e) => StartServer();
        stopButton.Click += (s, e) => StopServer();
        pageButton.Click += (s, e) => OpenPage();
        refreshButton.Click += (s, e) => Refresh(true);

        logBox.Multiline = true;
        logBox.ReadOnly = true;
        logBox.ScrollBars = ScrollBars.Vertical;
        logBox.Dock = DockStyle.Fill;
        logBox.Font = new Font("Consolas", 9f);
        logBox.BackColor = SystemColors.Window;

        grid.Controls.Add(stateLabel, 0, 0);
        grid.Controls.Add(envLabel, 0, 1);
        grid.Controls.Add(rootRow, 0, 2);
        grid.Controls.Add(buttons, 0, 3);
        grid.Controls.Add(logBox, 0, 4);
        Controls.Add(grid);

        // Состояние спрашивается по кнопке и после каждого действия. Таймер нужен только
        // пока ждём, когда поднятый нами сервер ответит, - и гаснет, как только ответил.
        timer.Interval = 1000;
        timer.Tick += (s, e) => { if (--waitTicks <= 0) timer.Stop(); Refresh(false); };
    }

    // -- жизнь окна --
    void OnLoad(object sender, EventArgs e)
    {
        string home = Module.FindHome(options.Home);
        if (home == null)
        {
            Fail("рядом нет " + Module.Script + ": назовите папку модуля доводом или переменной MORPHBENCH_HOME");
            return;
        }
        string python = Module.FindPython(home);
        if (python == null)
        {
            Fail("не нашёл python.exe: назовите его переменной MORPHBENCH_PYTHON или ключом \"python\" в morphbench.json");
            return;
        }
        launcher = new Launcher(home, python) { Log = Append };
        remembered = new Remembered(home);
        Append("модуль: " + home);
        Append("python: " + python);
        stateLabel.Text = "спрашиваю состояние…";
        SetButtons(false);
        ThreadPool.QueueUserWorkItem(_ =>
        {
            var st = launcher.StatusFromCli();
            BeginInvoke((Action)(() => AfterFirstStatus(st)));
        });
    }

    void AfterFirstStatus(ServerStatus st)
    {
        status = st;
        if (st.Error != null) Append(st.Error);
        // Под MO2 корень - Data игры, которую видит этот процесс; вне MO2 - корень уже
        // поднятого сервера, а если его нет - что помним.
        rootBox.Text = !string.IsNullOrEmpty(options.Root) ? options.Root
            : st.HereInsideMo2 ? (st.HereDataRoot ?? "")
            : (st.Up && !string.IsNullOrEmpty(st.Root)) ? st.Root : remembered.Root;
        Show(st);
        if (options.Start) StartServer();
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        timer.Stop();
        // Сервер, поднятый этим окном, уходит вместе с ним: иначе из-под MO2 остался бы
        // невидимый процесс, и MO2 ждала бы его.
        if (launcher != null && launcher.Owns) launcher.Stop();
    }

    void Fail(string message)
    {
        stateLabel.Text = "morphbench: " + message;
        stateLabel.ForeColor = Color.Firebrick;
        SetButtons(false);
        Append(message);
    }

    // -- действия: каждое - вызов сервера, тот же, что у командной строки --
    void StartServer()
    {
        if (launcher == null) return;
        if (status.Up)
        {
            HandOver();
            return;
        }
        if (status.State == "busy")
        {
            Append("порт занят другой программой: " + status.Url + " - смените servePort в morphbench.json");
            return;
        }
        string root = rootBox.Text.Trim();
        try
        {
            launcher.Start(root.Length > 0 ? root : null);
        }
        catch (Exception e)
        {
            Append("не удалось запустить: " + e.Message);
            return;
        }
        if (!status.HereInsideMo2 && root.Length > 0) { remembered.Root = root; remembered.Save(); }
        stateLabel.Text = "поднимаю…";
        // Страницу открываем, как только сервер ответит, - см. Refresh.
        pendingOpen = options.Start;
        options.Start = false;
        waitTicks = 60;
        timer.Start();
        Refresh(true);
    }

    bool pendingOpen;

    /// Сервер уже поднят - подключиться к нему и передать корень обзора. Вызов тот же,
    /// что и при подъёме, поэтому нажатие «Поднять» идемпотентно: поднят сервер или нет,
    /// окно делает одно и то же, а разбирается в этом команда.
    void HandOver()
    {
        string root = rootBox.Text.Trim();
        bool open = options.Start;
        options.Start = false;
        stateLabel.Text = "сервер поднят - передаю корень…";
        SetButtons(false);
        ThreadPool.QueueUserWorkItem(_ =>
        {
            string outp;
            try { outp = launcher.HandOver(root); }
            catch (Exception e) { outp = "передать корень не удалось: " + e.Message; }
            BeginInvoke((Action)(() =>
            {
                Append(outp.Trim().Length > 0 ? outp.Trim() : "сервер уже поднят: " + status.Url);
                if (open) OpenPage();
                Refresh(true);
            }));
        });
    }

    void StopServer()
    {
        if (launcher == null || !status.Up) { Append("сервер не поднят"); return; }
        stateLabel.Text = "останавливаю…";
        SetButtons(false);
        ThreadPool.QueueUserWorkItem(_ =>
        {
            launcher.Stop();
            BeginInvoke((Action)(() => { Append("остановлен: " + status.Url); Refresh(true); }));
        });
    }

    void OpenPage()
    {
        if (launcher == null) return;
        if (!status.Up) { Append("сервер не поднят - страницу открывать не с чего"); return; }
        try { launcher.OpenPage(); Append("страница: " + status.Url); }
        catch (Exception e) { Append("не открылась страница: " + e.Message); }
    }

    void Browse()
    {
        using (var dlg = new FolderBrowserDialog())
        {
            dlg.Description = "Папка обзора: под ней ищутся меши с файлами морфов";
            dlg.ShowNewFolderButton = false;
            if (rootBox.Text.Trim().Length > 0 && Directory.Exists(rootBox.Text.Trim())) dlg.SelectedPath = rootBox.Text.Trim();
            if (dlg.ShowDialog(this) == DialogResult.OK) rootBox.Text = dlg.SelectedPath;
        }
    }

    void Apply()
    {
        if (launcher == null) return;
        string root = rootBox.Text.Trim();
        if (root.Length == 0) { Append("назовите папку"); return; }
        if (!status.HereInsideMo2) { remembered.Root = root; remembered.Save(); }
        if (!status.Up) { Append("корень запомнен; сервер не поднят - он возьмёт папку при подъёме"); return; }
        stateLabel.Text = "обход " + root + "…";
        SetButtons(false);
        ThreadPool.QueueUserWorkItem(_ =>
        {
            string message;
            try
            {
                var got = launcher.SetRoot(root);
                object meshes;
                got.TryGetValue("meshes", out meshes);
                message = "обзор: " + root + " (" + meshes + " мешей)";
            }
            catch (Exception e)
            {
                message = "сервер отказал: " + e.Message;
            }
            BeginInvoke((Action)(() => { Append(message); Refresh(true); }));
        });
    }

    // -- состояние: опрос в фоне, показ в окне --
    void Refresh(bool now)
    {
        if (launcher == null || probing) return;
        probing = true;
        var previous = status;
        ThreadPool.QueueUserWorkItem(_ =>
        {
            ServerStatus st;
            try { st = launcher.Probe(previous); }
            catch (Exception e) { st = new ServerStatus { State = "busy", Error = e.Message, Url = launcher.Url }; }
            BeginInvoke((Action)(() =>
            {
                probing = false;
                bool cameUp = st.Up && !previous.Up;
                status = st;
                Show(st);
                if (st.Up) timer.Stop();
                if (cameUp && pendingOpen) { pendingOpen = false; OpenPage(); }
            }));
        });
    }

    void Show(ServerStatus st)
    {
        string state;
        Color colour;
        switch (st.State)
        {
            case "ours":
                state = "поднят  " + st.Url + (launcher != null && launcher.Owns ? "  (этим окном)" : "  (другим процессом)");
                colour = Color.ForestGreen;
                break;
            case "busy":
                state = "порт занят другой программой  " + st.Url;
                colour = Color.Firebrick;
                break;
            case "slow":
                state = "кто-то есть, но не отвечает  " + st.Url + "  (сервер за обходом большой папки?)";
                colour = Color.DarkOrange;
                break;
            default:
                state = "не поднят  " + st.Url;
                colour = SystemColors.ControlText;
                break;
        }
        stateLabel.Text = "Сервер: " + state;
        stateLabel.ForeColor = colour;
        var env = new StringBuilder();
        env.Append("это окно под MO2: ").Append(st.HereInsideMo2 ? "да" : "нет");
        if (!string.IsNullOrEmpty(st.HereDataRoot)) env.Append(" · Data игры: ").Append(st.HereDataRoot);
        if (st.Up)
        {
            env.Append(" · сервер под MO2: ").Append(st.InsideMo2 == true ? "да" : "нет");
            env.Append(" · корень: ").Append(string.IsNullOrEmpty(st.Root) ? "не задан" : st.Root);
            if (st.Meshes != null) env.Append(" (").Append(st.Meshes).Append(" мешей)");
        }
        envLabel.Text = env.ToString();
        if (st.Up && st.HereInsideMo2 && st.InsideMo2 == false)
        {
            if (!warnedForeign)
                Append("сервер поднят вне MO2 и не видит мешей сборки: остановите его и поднимите отсюда");
            warnedForeign = true;
        }
        else if (!st.Up) warnedForeign = false;
        SetButtons(true);
        startButton.Enabled = !st.Up && st.State != "busy" && st.State != "slow";
        stopButton.Enabled = st.Up;
        pageButton.Enabled = st.Up;
        applyButton.Enabled = true;
    }

    void SetButtons(bool on)
    {
        startButton.Enabled = stopButton.Enabled = pageButton.Enabled = applyButton.Enabled = on;
    }

    void Append(string line)
    {
        if (InvokeRequired) { BeginInvoke((Action<string>)Append, line); return; }
        if (logBox.TextLength > 200000) logBox.Clear();
        logBox.AppendText(line + Environment.NewLine);
    }
}
