import pandas as pd
import matplotlib.pyplot as plt

# Leer el CSV
df = pd.read_csv('pura_curva.csv')



plt.figure(figsize=(8, 8))
plt.scatter(df['x_px'], df['y_px'], c=df['t_s'], cmap='viridis', s=50)
plt.colorbar(label='Tiempo (s)')
plt.xlabel('X (píxeles)')
plt.ylabel('Y (píxeles)')
plt.title('Trayectoria espacial')
plt.axis('equal')
plt.grid(True, alpha=0.3)
plt.show()