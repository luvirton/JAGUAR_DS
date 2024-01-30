import pandas as pd
import json

# Asegúrate de tener la ruta correcta del archivo de autonomias
autonomia_df = pd.read_excel('autonomias2.xls')

# Leer el archivo de entrenamiento para las tareas y las fechas de vencimiento
entrenamiento_df = pd.read_excel('entrenamiento.xls')

# Preparar y limpiar los datos de entrenamiento_df para tener la tarea más reciente por cargo
entrenamiento_df_sorted = entrenamiento_df.sort_values(by=['Cargo', 'Fecha Vence'], ascending=[True, False])
entrenamiento_df_filtered = entrenamiento_df_sorted.drop_duplicates(subset=['Nombre','Cargo', 'Codigo Tarea'])

# Agrupar la información de autonomia_df por las columnas relevantes
grouped_autonomia = autonomia_df.groupby(['Numero Identificacion', 'Nombre Completo', 'Grado', 'UNIDAD'])

# Construir la estructura JSON
workers_data = {"Workers": []}

for (id, name, rank, unit), group in grouped_autonomia:
    # Filtrar las tareas relevantes para este trabajador específico y su cargo en entrenamiento_df_filtered
    worker_tasks = entrenamiento_df_filtered[entrenamiento_df_filtered['Nombre'] == name]
      
    # Obtener habilidades y fechas válidas
    skills = []
    for cargo in group['Cargo'].unique():
        cargo_tasks = worker_tasks[worker_tasks['Cargo'] == cargo]
        tasks = [{
            "TaskCode": row['Codigo Tarea'], 
            "Validity": row['Fecha Vence'].strftime('%Y-%m-%d')
        } for _, row in cargo_tasks.iterrows()]

        # Encuentra la fecha de fin correspondiente al cargo actual del grupo.
        validity_date = group.loc[group['Cargo'] == cargo, 'Fecha fin'].max().strftime('%Y-%m-%d')

        # Agregar habilidad y tareas a la lista de habilidades
        skills.append({
            "Skill": cargo, 
            "Validity": validity_date,  # fecha de vencimiento del cargo
            "Tasks": tasks
        })

    # Agregar trabajador al JSON
    workers_data["Workers"].append({
        "Id": int(id),
        "Name": name,
        "Rank": rank,
        "Unit": unit,
        "Skills": skills
    })

# Guardar la estructura en el archivo JSON
with open("workers.json", "w") as file:
    json.dump(workers_data, file, ensure_ascii=False, indent=4)
