import pandas as pd
import matplotlib.pyplot as plt

# Leer el CSV
df = pd.read_csv('pura_curva.csv')



fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))

# Gráfico 1: Presión vs tiempo
ax1.plot(df['t_s'], df['pura_cmH2O'], 'b-', linewidth=2)
ax1.fill_between(df['t_s'], df['pura_min_cmH2O'], df['pura_max_cmH2O'], 
                  alpha=0.3, color='blue')
ax1.set_xlabel('Tiempo (s)')
ax1.set_ylabel('Presión (cmH₂O)')
ax1.grid(True, alpha=0.3)

# Gráfico 2: Posición espacial
scatter = ax2.scatter(df['x_px'], df['y_px'], c=df['t_s'], cmap='viridis', s=50)
ax2.set_xlabel('X (píxeles)')
ax2.set_ylabel('Y (píxeles)')
ax2.set_title('Trayectoria')
fig.colorbar(scatter, ax=ax2, label='Tiempo (s)')

plt.tight_layout()
plt.show()