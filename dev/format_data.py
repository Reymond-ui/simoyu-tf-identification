import numpy as np
from tkinter import filedialog


DELIMETER = ','

def read_csv_data(file_path):
    arr = np.genfromtxt(file_path, delimiter=DELIMETER, comments='#', dtype=float)
    mask = ~np.isnan(arr).any(axis=1)
    arr  = arr[mask]
    for i in range(len(arr[0])):
        print(i)
        print(arr[:, i][:100])
        print('/////////////////////////')

#t, cmd, dat = arr[:, 0], arr[:, 1], arr[:, 2]



file_path = filedialog.askopenfilename(
        title = "Выберите файл",
        filetypes = (("ALL files", "*"), ("CSV files","*.csv"), ("BAG files", "*.bag"))
    )
read_csv_data(file_path)
