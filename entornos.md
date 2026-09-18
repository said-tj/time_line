# analisis_presion
### Crear un entorno
```
conda create -n analisis_presion python=3.11
```
### Activar entorno
```
conda activate analisis_presion
```

Uso del script _piloto_:
```
python3 extraer_pura.py a_2.png -o pura.csv --plot verificacion.png
python3 extraer_pura.py a_1.png -o pura.csv --px-por-seg 7.1092 --x-t0 31.15
```