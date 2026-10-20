# =======================================================================================================================
#
#             ©2026, "Crop - utility"
#               by Zheltyakov T.A.
#
# =======================================================================================================================
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---- импорт из основной программы ----------------------------------------
from main import read_bag_data, read_csv_data

# =======================================================================================================================
class CropApp:
    def __init__(self, root):
        self.root = root
        root.title("Crop CSV / BAG")
        root.geometry("700x700+700+0")

        # ---------------- панель управления ----------------
        ctrl = tk.Frame(root)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        row1 = tk.Frame(ctrl)
        row1.pack(side=tk.TOP, fill=tk.X)

        tk.Button(row1, text="Выбрать файл", command=self.choose_file).pack(side=tk.LEFT)

        #self.file_label = tk.Label(ctrl, text="(файл не выбран)", anchor="w", fg="gray")
        #self.file_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        tk.Label(row1, text="t от:").pack(side=tk.LEFT)
        self.t_from = tk.Entry(row1, width=10)
        self.t_from.pack(side=tk.LEFT, padx=(2, 10))

        tk.Label(row1, text="t до:").pack(side=tk.LEFT)
        self.t_to = tk.Entry(row1, width=10)
        self.t_to.pack(side=tk.LEFT, padx=(2, 10))

        tk.Button(row1, text="Обновить вид", command=self.draw).pack(side=tk.LEFT, padx=4)
        tk.Button(row1, text="Сохранить CSV", command=self.save_csv, bg="#d9f2d9").pack(side=tk.LEFT, padx=4)

        self.file_label = tk.Label(ctrl, text="(файл не выбран)",
                                   anchor="w", fg="gray", justify="left")
        self.file_label.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))

        self.fig = Figure(figsize=(10, 6.5), dpi=100)
        self.ax1 = self.fig.add_subplot(2, 1, 1)   # весь сигнал
        self.ax2 = self.fig.add_subplot(2, 1, 2)   # вырезанный фрагмент

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.file_path = None
        self.t = self.cmd = self.data = None
# =======================================================================================================================
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=(("ALL files", "*"),
                       ("CSV files", "*.csv"),
                       ("BAG files", "*.bag")))
        if not path:
            return

        try:
            lower = path.lower()
            if lower.endswith(".bag"):
                t, cmd, data = read_bag_data(path)
            elif lower.endswith(".csv"):
                t, cmd, data = read_csv_data(path)
            else:
                messagebox.showerror("Ошибка", "Неверный тип файла")
                return
        except Exception as e:
            messagebox.showerror("Ошибка чтения", str(e))
            return
        if len(path) > 95:
            head = path[:30]
            tail = path[-(95 - 33):]
            path_name = f"{head}...{tail}"
        else:
            path_name = path

        self.file_path = path
        self.file_label.config(text=path_name, fg="black")
        self.t, self.cmd, self.data = t, cmd, data

        # автозаполнение границ = весь диапазон
        self.t_from.delete(0, tk.END)
        self.t_from.insert(0, f"{t[0]:.4f}")
        self.t_to.delete(0, tk.END)
        self.t_to.insert(0, f"{t[-1]:.4f}")

        self.draw()
# =======================================================================================================================
    def _parse_bounds(self):
        try:
            t_from = float(self.t_from.get().replace(",", "."))
            t_to   = float(self.t_to.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректные значения времени")
            return None
        if t_from >= t_to:
            messagebox.showerror("Ошибка", "t 'от' должно быть меньше t 'до'")
            return None
        return t_from, t_to
# =======================================================================================================================
    def draw(self):
        if self.t is None:
            return

        bounds = self._parse_bounds()
        if bounds is None:
            return
        t_from, t_to = bounds

        # ---- верхний график: весь сигнал + выделенный фрагмент ----
        self.ax1.clear()
        self.ax1.plot(self.t, self.cmd,  'b', linewidth=1, label='cmd')
        self.ax1.plot(self.t, self.data, 'k', linewidth=1, label='data')
        self.ax1.axvspan(t_from, t_to, color='orange', alpha=0.15,
                         label='фрагмент')
        self.ax1.axvline(t_from, color='r', linestyle='--', linewidth=1)
        self.ax1.axvline(t_to,   color='r', linestyle='--', linewidth=1)
        self.ax1.grid(True)
        self.ax1.legend(loc='best')
        self.ax1.set_xlabel('t, c')
        self.ax1.set_ylabel('y')
        self.ax1.set_title(Path(self.file_path).name if self.file_path else '')

        # ---- нижний график: только вырезанный фрагмент ----
        m = (self.t >= t_from) & (self.t <= t_to)
        self.ax2.clear()
        if m.any():
            self.ax2.plot(self.t[m], self.cmd[m],  'b', linewidth=1, label='cmd')
            self.ax2.plot(self.t[m], self.data[m], 'k', linewidth=1, label='data')
        self.ax2.grid(True)
        self.ax2.legend(loc='best')
        self.ax2.set_xlabel('t, c')
        self.ax2.set_ylabel('y')
        self.ax2.set_title(
            f'{t_from:.4f} .. {t_to:.4f} c   ({int(m.sum())} точек)')

        self.fig.tight_layout()
        self.canvas.draw_idle()
# =======================================================================================================================
    def save_csv(self):
        if self.t is None:
            messagebox.showwarning("Внимание", "Сначала выберите файл")
            return

        bounds = self._parse_bounds()
        if bounds is None:
            return
        t_from, t_to = bounds

        m = (self.t >= t_from) & (self.t <= t_to)
        if not m.any():
            messagebox.showwarning("Внимание", "В диапазоне нет точек")
            return

        # время фрагмента начинаем с нуля
        t_crop    = self.t[m] - self.t[m][0]
        cmd_crop  = self.cmd[m]
        data_crop = self.data[m]

        initial = (Path(self.file_path).stem + "_crop.csv"
                   if self.file_path else "crop.csv")

        out_path = filedialog.asksaveasfilename(
            title="Сохранить CSV",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"), ("ALL files", "*")),
            initialfile=initial)
        if not out_path:
            return

        out = np.column_stack([t_crop, cmd_crop, data_crop])
        np.savetxt(out_path, out, delimiter=';', fmt='%.6f', header='time;cmd;data', comments='#')

        print(f"Сохранено {len(t_crop)} точек -> {out_path}")
        messagebox.showinfo("Готово",f"Сохранено {len(t_crop)} точек в\n{out_path}")
# =======================================================================================================================

def main():
    root = tk.Tk()
    CropApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()