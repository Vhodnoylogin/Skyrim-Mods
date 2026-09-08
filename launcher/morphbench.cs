// morphbench.exe - точка входа для Mod Organizer 2.
//
// Зачем он нужен. MO2 подменяет файловую систему только тем процессам, которые запустил
// сам (и их потомкам): моды сливаются в один Data игры библиотекой usvfs. Чтобы верстак
// увидел меши всей сборки, его надо запустить из MO2 - а MO2 запускает исполняемые файлы,
// не скрипты. Этот файл и есть такой исполняемый: он находит Python и модуль, зовёт
// `python mb.py serve` из-под usvfs и ждёт его. Всё остальное - дело `serve`: он сам
// поднимает сервер, если тот ещё не поднят, либо отдаёт уже поднятому Data игры.
//
// Ни одного пути внутри. Модуль - рядом с exe (там лежит mb.py), либо папка первым
// доводом, либо переменная MORPHBENCH_HOME. Python - переменная MORPHBENCH_PYTHON, ключ
// "python" в morphbench.json, python.exe по PATH (кроме заглушки магазина Windows),
// реестр PythonCore, либо запускатель py.exe.
//
// Сборка - штатным компилятором .NET Framework, который есть на любой Windows:
//     launcher\build.cmd
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using Microsoft.Win32;

static class Launcher
{
    const string Module = "mb.py";

    static int Main(string[] args)
    {
        string home = FindHome(args);
        if (home == null)
        {
            Console.Error.WriteLine("morphbench: рядом нет " + Module + "; назовите папку модуля "
                + "первым доводом или переменной MORPHBENCH_HOME");
            return 2;
        }
        string python = FindPython(home);
        if (python == null)
        {
            Console.Error.WriteLine("morphbench: не нашёл python.exe; назовите его переменной "
                + "MORPHBENCH_PYTHON или ключом \"python\" в morphbench.json");
            return 2;
        }
        var start = new ProcessStartInfo(python, Quote(Path.Combine(home, Module)) + " serve")
        {
            UseShellExecute = false,
            WorkingDirectory = home,
        };
        Console.WriteLine("morphbench: " + python + " " + start.Arguments);
        try
        {
            using (var proc = Process.Start(start))
            {
                proc.WaitForExit();
                return proc.ExitCode;
            }
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("morphbench: не удалось запустить " + python + ": " + e.Message);
            return 2;
        }
    }

    // ---- где модуль -------------------------------------------------------------------
    static string FindHome(string[] args)
    {
        var candidates = new List<string>();
        if (args.Length > 0) candidates.Add(args[0]);
        string env = Environment.GetEnvironmentVariable("MORPHBENCH_HOME");
        if (!string.IsNullOrEmpty(env)) candidates.Add(env);
        candidates.Add(AppDomain.CurrentDomain.BaseDirectory);
        candidates.Add(Directory.GetCurrentDirectory());
        foreach (string dir in candidates)
        {
            try
            {
                string full = Path.GetFullPath(dir);
                if (File.Exists(Path.Combine(full, Module))) return full;
            }
            catch (Exception) { }
        }
        return null;
    }

    // ---- где Python -------------------------------------------------------------------
    static string FindPython(string home)
    {
        string env = Environment.GetEnvironmentVariable("MORPHBENCH_PYTHON");
        if (IsFile(env)) return env;

        string fromConfig = PythonFromConfig(Path.Combine(home, "morphbench.json"));
        if (IsFile(fromConfig)) return fromConfig;

        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string dir in path.Split(Path.PathSeparator))
        {
            if (dir.Trim().Length == 0) continue;
            // Заглушка магазина Windows лежит в WindowsApps: без настоящего Python
            // она открывает магазин вместо того, чтобы что-то запустить.
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
            // Настройки читает сам верстак; здесь нужен один ключ, и разбирать ради него
            // весь JSON незачем: путь в двойных кавычках, косые в нём экранированы.
            var m = Regex.Match(File.ReadAllText(json), "\"python\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            if (!m.Success) return null;
            return Regex.Unescape(m.Groups[1].Value);
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

    static bool IsFile(string path)
    {
        try { return !string.IsNullOrEmpty(path) && File.Exists(path); }
        catch (Exception) { return false; }
    }

    static string Quote(string s)
    {
        return "\"" + s.Replace("\"", "\\\"") + "\"";
    }
}
