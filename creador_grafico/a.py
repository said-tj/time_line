import pandas as pd
import matplotlib.pyplot as plt

# Leer el CSV
df = pd.read_csv('pura_curva_0p25s.csv')

# Crear figura
plt.figure(figsize=(12, 6))

# Graficar presión central con banda de min-max
plt.plot(df['t_s'], df['pura_cmH2O'], 'b-', label='Presión', linewidth=2)
plt.fill_between(df['t_s'], df['pura_min_cmH2O'], df['pura_max_cmH2O'], 
                  alpha=0.3, color='blue', label='Rango (min-max)')

plt.xlabel('Tiempo (s)')
plt.ylabel('Presión (cmH₂O)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()