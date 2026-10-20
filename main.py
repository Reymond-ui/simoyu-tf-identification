#=======================================================================================================================
#
#        ©2026, "Simoyu transfer function identification"
#                         by Zheltyakov T.A.
#
#=======================================================================================================================

# Для повторной установки удалите файл-флаг ".installed"
#import installer
#installer.check_install()

#=======================================================================================================================

import math
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from rosbags.highlevel import AnyReader
from control import tf, step_response

#=======================================================================================================================

DT_STEP = 0.01          # Шаг дискретизации
M_ORDER = 1             # Степень числителя
N_ORDER = 2             # Степень знаменателя
CMD_TOPIC  = '/cmd_vel_stamp'
DATA_TOPIC = '/odo_tf/pubtop'

VAL_PATHS = [
    ['Twist', 'Linear', 'X'],
    ['Twist','Twist','Linear','X'],
    ['twist', 'linear', 'x'],
    ['twist','twist','linear','x'],
    ['Linear', 'X']
]

#=======================================================================================================================

def _extract_value(msg):
    for path in VAL_PATHS:
        obj = msg
        for attr in path:
            obj = getattr(obj, attr, None)
            if obj == None:
                break
        if obj is not None:
            return float(obj)
    raise AttributeError(f"not founded anything like {VAL_PATHS}")

def _poly_to_str(coeffs, prec=4):
    coeffs = np.asarray(coeffs).flatten()
    power = len(coeffs) - 1
    parts = []
    for i, c in enumerate(coeffs):
        p = power - i
        if abs(c) < 1e-12:
            continue
        sign = '-' if c < 0 else '+'
        a = abs(c)
        if p == 0:
            body = f"{a:.{prec}g}"
        elif p == 1:
            body = f"{a:.{prec}g}*s"
        else:
            body = f"{a:.{prec}g}*s^{p}"
        if not parts:
            parts.append(('-' if sign == '-' else '') + body)
        else:
            parts.append(f" {sign} {body}")
    return "".join(parts) if parts else "0"

def _format_tf(W, prec=4):
    num = np.asarray(W.num[0][0]).flatten()
    den = np.asarray(W.den[0][0]).flatten()
    return f"({_poly_to_str(num, prec)}) / ({_poly_to_str(den, prec)})"

#=======================================================================================================================

def read_bag_data(file_path, dt=DT_STEP):

    cmd_t, cmd_v   = [], []
    data_t, data_v = [], []

    with AnyReader([Path(file_path)]) as reader:
        cmd_conns  = [c for c in reader.connections if c.topic == CMD_TOPIC]
        data_conns = [c for c in reader.connections if c.topic == DATA_TOPIC]

        for conn, ts, raw in reader.messages(connections=cmd_conns):
            msg = reader.deserialize(raw, conn.msgtype)
            cmd_t.append(ts * 1e-9)
            cmd_v.append(_extract_value(msg))

        for conn, ts, raw in reader.messages(connections=data_conns):
            msg = reader.deserialize(raw, conn.msgtype)
            data_t.append(ts * 1e-9)
            data_v.append(_extract_value(msg))

    cmd_t  = np.asarray(cmd_t);  cmd_v  = np.asarray(cmd_v)
    data_t = np.asarray(data_t); data_v = np.asarray(data_v)

    if cmd_t.size == 0:
        raise ValueError(f"{CMD_TOPIC} is empty")
    if data_t.size == 0:
        raise ValueError(f"{DATA_TOPIC} is empty")

    t0 = min(cmd_t[0], data_t[0])
    t1 = max(cmd_t[-1], data_t[-1])
    t    = np.arange(t0, t1, dt)
    cmd  = np.interp(t, cmd_t,  cmd_v)
    data = np.interp(t, data_t, data_v)
    return t - t[0], cmd, data

def read_csv_data(file_path):

    arr = np.genfromtxt(file_path, delimiter=';', comments='#', dtype=float)

    if arr.ndim == 1:
        arr = np.genfromtxt(file_path, delimiter=',', comments='#', dtype=float)
        if arr.ndim == 1:
            raise ValueError("CSV must have 3 columns: time, cmd, data")
    if arr.shape[1] < 3:
        raise ValueError(f"CSV must have 3 columns, got {arr.shape[1]}")

    mask = ~np.isnan(arr).any(axis=1)
    arr  = arr[mask]
    t, cmd, dat = arr[:, 0], arr[:, 1], arr[:, 2]
    return t - t[0], cmd, dat

#=======================================================================================================================

# Выделяем интервал при котором подавалось максимальное воздействие и нормируем данные в этом диапозоне
# Для защиты от всплесков устанавливаем чувствительность SENS (default=10) (минимальный размер полки)
def process_step(cmd_queue, data_queue, dt=DT_STEP):
    SENS = 10
    if cmd_queue.size == 0:
        raise ValueError(f"{CMD_TOPIC} is empty")
    if data_queue.size == 0:
        raise ValueError(f"{DATA_TOPIC} is empty")

    max_value = np.max(cmd_queue)
    if max_value == 0:
        raise ValueError(f"{CMD_TOPIC} max value = 0")

    idx = np.where(np.isclose(cmd_queue, max_value))[0]
    if idx.size == 0:
        raise ValueError(f"{CMD_TOPIC} step was not found")

    index_first = idx[0]
    index_last  = idx[-1]

    if (index_last - index_first) < SENS:
        new_idx = np.where(np.isclose(cmd_queue[index_last + 1:], max_value))[0]
        if new_idx.size != 0:
            index_last += new_idx[-1] + 1

    y_norm = data_queue[index_first:index_last + 1] / max_value

    zero_idx = np.where(y_norm == 0)[0]
    if zero_idx.size != 0:
        index_e_first = zero_idx[0]
        index_e_last  = zero_idx[-1] - 1
    else:
        index_e_first = 0
        index_e_last  = 0
    delay = DT_STEP * (index_e_last - index_e_first)
    print(f"Запаздывание/delay: {delay}")

    y_norm = y_norm[index_e_last:]
    tfin = len(y_norm)
    t = np.arange(0, tfin, DT_STEP)
    t = t[:len(y_norm)]
    return y_norm, t, delay

#=======================================================================================================================

def simoyu(n, m, y_norm, t):
    y_norm = np.asarray(y_norm)
    t = np.asarray(t)

    N = n + m
    S = np.zeros(N)

    for k in range(1, N + 1):
        Sdd = 0.0
        for i in range(0, k - 1):
            Sdd += S[k - 2 - i] * ((-t) ** i / math.factorial(i))
        rX = (1.0 - y_norm) * (Sdd + ((-t) ** (k - 1)) / math.factorial(k - 1))
        S[k - 1] = np.trapezoid(rX, t)

    A = np.zeros((N, N))
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            if j <= m:
                if i == j:
                    A[i - 1, j - 1] = 1.0
                elif i > j:
                    A[i - 1, j - 1] = S[i - j - 1]
            else:
                if i == j - m:
                    A[i - 1, j - 1] = -1.0
    B = -S
    try:
        x = np.linalg.solve(A, B)
    except np.linalg.LinAlgError:
        x, *_ = np.linalg.lstsq(A, B, rcond=None)
    return S, x

def id_tf(n, m, y_norm, t):
    S, X = simoyu(n, m, y_norm, t)
    if m > 0:
        num = np.concatenate([X[m - 1::-1], [1.0]])
    else:
        num = np.array([1.0])
    den = np.concatenate([X[n + m - 1:m - 1:-1], [1.0]])
    W = tf(num, den)

    res   = step_response(W, t)
    t_kon = np.asarray(res.time).flatten()
    y_kon = np.asarray(res.outputs).flatten()
    return W, t_kon, y_kon

#=======================================================================================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("Simoyu identification")
        root.geometry("700x700+0+0")

        ctrl = tk.Frame(root)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        tk.Button(ctrl, text="Выбрать файл", command=self.choose_file)\
            .pack(side=tk.LEFT)

        self.file_label = tk.Label(ctrl, text="(файл не выбран)",
                                   anchor="w", fg="gray")
        self.file_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        tk.Label(ctrl, text="M_ORDER:").pack(side=tk.LEFT)
        self.m_entry = tk.Entry(ctrl, width=5)
        self.m_entry.insert(0, str(M_ORDER))
        self.m_entry.pack(side=tk.LEFT, padx=(2, 10))

        tk.Label(ctrl, text="N_ORDER:").pack(side=tk.LEFT)
        self.n_entry = tk.Entry(ctrl, width=5)
        self.n_entry.insert(0, str(N_ORDER))
        self.n_entry.pack(side=tk.LEFT, padx=(2, 10))

        tk.Button(ctrl, text="Обработать", command=self.process)\
            .pack(side=tk.LEFT)

        self.fig = Figure(figsize=(9, 6), dpi=100)
        self.ax1 = self.fig.add_subplot(2, 1, 1)   # переходный процесс
        self.ax2 = self.fig.add_subplot(2, 1, 2)   # |Δy|

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.file_path = None

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=(("ALL files", "*"),
                       ("CSV files", "*.csv"),
                       ("BAG files", "*.bag"))
        )
        if path:
            self.file_path = path
            self.file_label.config(text=path, fg="black")
            print(path)

    def process(self):
        if not self.file_path:
            messagebox.showwarning("Внимание", "Сначала выберите файл")
            return

        try:
            n = int(self.n_entry.get())
            m = int(self.m_entry.get())
            if n < 0 or m < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка",
                                 "N_ORDER и M_ORDER должны быть целыми >= 0")
            return

        # --- чтение ---
        delay = 0.0
        try:
            if self.file_path.lower().endswith(".bag"):
                _, cmd_queue, data_queue = read_bag_data(self.file_path, DT_STEP)
            elif self.file_path.lower().endswith(".csv"):
                _, cmd_queue, data_queue = read_csv_data(self.file_path)
            else:
                messagebox.showerror("Ошибка", "Неверный тип файла")
                return
            y_norm, t, delay = process_step(cmd_queue, data_queue, DT_STEP)
        except Exception as e:
            messagebox.showerror("Ошибка чтения", str(e))
            return

        if y_norm.size < n + m + 1:
            messagebox.showerror("Ошибка", "Слишком короткие данные")
            return

        # --- идентификация ---
        try:
            W, t_kon, y_kon = id_tf(n, m, y_norm, t)
        except Exception as e:
            messagebox.showerror("Ошибка идентификации", str(e))
            return

        self.update_plots(t, y_norm, t_kon, y_kon, W, delay)

    def update_plots(self, t, y_norm, t_kon, y_kon, W, delay=0.0):
        min_len = min(len(t), len(y_norm), len(t_kon), len(y_kon))
        t_plot  = t[:min_len]
        y_plot  = y_norm[:min_len]
        t_kon   = t_kon[:min_len]
        y_kon   = y_kon[:min_len]

        dev   = np.abs(y_kon - y_plot)
        delta = float(np.nanmean(dev))

        print(f"Запаздывание: tau = {delay:2.2f}")
        print(f"W = {W}")
        tf_str = _format_tf(W)

        # --- верхний график ---
        self.ax1.clear()
        self.ax1.plot(t_plot, y_plot, 'k', linewidth=1,
                      label='Переходный процесс')
        self.ax1.plot(t_kon, y_kon, 'r', linewidth=1, label=tf_str)
        self.ax1.grid(True)
        self.ax1.legend()
        self.ax1.set_xlabel('t, c')
        self.ax1.set_ylabel('y')
        self.ax1.set_title(f'delay = {delay:.4g}')

        # --- нижний график ---
        self.ax2.clear()
        self.ax2.plot(t_plot, dev, 'k', linewidth=1, label='|Δy|')
        self.ax2.grid(True)
        self.ax2.legend()
        self.ax2.set_xlabel('t, c')
        self.ax2.set_ylabel('|Δy|')
        self.ax2.set_title(f'delta = {delta:.4g}')

        self.fig.tight_layout()
        self.canvas.draw_idle()
# =======================================================================================================================

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()