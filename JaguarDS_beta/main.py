import sys
import pandas as pd
import numpy as np
import json
import csv
import seaborn as sns
from PyQt5 import QtWidgets, uic,QtCore, QtGui
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QGroupBox, QCheckBox,QPushButton,QTreeWidget,QTreeWidgetItem
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import pyqtSignal
import calendar
import datetime

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class MiApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('jaguards.ui', self)

        self.request_dialog = None  # Inicializa la referencia del diálogo de solicitudes
        self.worker_stats_dialog = None  # referencia a dialogo de estadísticas de trabajador para que se pueda actualizar por medio de la clase de solicitudes
        self.stats_graph_dialog = None


        # ... inicialización variables para gráfico de torta
        self.days_in_month = None
        self.worker_series = None
        self.worker = None
        self.year = None
        # Agrega un atributo para el eje del gráfico de torta
        self.pie_ax = None

        # Encuentra los widgets por sus nombres
        self.userLabel = self.findChild(QtWidgets.QLabel, "userLabel")
        self.requestButton = self.findChild(QtWidgets.QPushButton, "requestButton")

        #-----Dialogo de login-------------------
        login_dialog = LoginDialog()
        if login_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.username = login_dialog.username  # Guarda el nombre de usuario
            self.userLabel.setText(f"Usuario: {self.username}")  # Actualiza el label con el nombre de usuario
            self.show()  # Muestra la ventana principal
        else:
            self.close()  # Cierra la aplicación si el inicio de sesión falla
        
        # Hacer referencia al QTableWidget creado desde el Qt Designer
        self.calendario = self.findChild(QtWidgets.QTableWidget, 'customCalendarWidget')

        # Conecta la acción del boton de sincronización
        self.syncButton.clicked.connect(self.synchronize_data)

        # Cargar todos los trabajadores desde el archivo JSON al inicio
        with open("workers.json", "r") as file:
            data = json.load(file)
            self.trabajadores = data["Workers"]

         # Inicializar el calendario
        self.initialize_calendar()

        self.calendario.cellClicked.connect(self.cell_clicked)

        self.temp_selected_indexes = []

        # Poblando el QComboBox de mes
        self.months = [calendar.month_name[i] for i in range(1, 13)]
        self.monthComboBox.addItems(self.months)

        # Poblando el QComboBox de año
        current_year = datetime.datetime.now().year
        years = [str(year) for year in range(current_year - 10, current_year + 11)]  # Rango desde 10 años antes hasta 10 años después
        self.yearComboBox.addItems(years)

        # Seleccionar el mes y año actuales
        current_month = datetime.datetime.now().month
        self.monthComboBox.setCurrentIndex(current_month - 1)  # Restamos 1 porque los índices empiezan en 0
        self.yearComboBox.setCurrentText(str(current_year))

        # Conectando los QComboBox a la función update_calendar
        self.monthComboBox.currentIndexChanged.connect(self.update_calendar)
        self.yearComboBox.currentIndexChanged.connect(self.update_calendar)
        
         # Conectando el boton Solicitudes con el dialogo de solicitudes
        self.requestButton.clicked.connect(self.show_request_dialog)

        # Inicializa el calendario
        self.update_calendar()

    def select_day_in_agenda(self, day):
        # Función para seleccionar la columna correspondiente en la agenda
        month_index = self.monthComboBox.currentIndex() + 1
        year = int(self.yearComboBox.currentText())

        # Comprueba si el día seleccionado corresponde al mes y año actuales
        if month_index == self.stats_graph_dialog.selected_month and year == self.stats_graph_dialog.selected_year:
            self.calendario.selectColumn(day)  # Selecciona la columna en QTableWidget

    def show_request_dialog(self):
        if not self.request_dialog:
            self.request_dialog = RequestDialog(self)  # Crea el diálogo si aún no existe
        self.request_dialog.exec_()

    def get_file_paths(self):
        options = QFileDialog.Options()
        autonomia_file, _ = QFileDialog.getOpenFileName(self, "Seleccione el archivo de autonomías", "", "Excel Files (*.xls *.xlsx)", options=options)
        entrenamiento_file, _ = QFileDialog.getOpenFileName(self, "Seleccione el archivo de entrenamiento", "", "Excel Files (*.xls *.xlsx)", options=options)
        return autonomia_file, entrenamiento_file    

    def synchronize_data(self):
        autonomia_file, entrenamiento_file = self.get_file_paths()
        if autonomia_file and entrenamiento_file:
            try:
                autonomia_df = pd.read_excel(autonomia_file)
                entrenamiento_df = pd.read_excel(entrenamiento_file)
                entrenamiento_df_sorted = entrenamiento_df.sort_values(by=['Cargo', 'Fecha Vence'], ascending=[True, False])
                entrenamiento_df_filtered = entrenamiento_df_sorted.drop_duplicates(subset=['Nombre','Cargo', 'Codigo Tarea'])
                grouped_autonomia = autonomia_df.groupby(['Numero Identificacion', 'Nombre Completo', 'Grado', 'UNIDAD'])

                # Leer el archivo JSON existente
                with open("workers.json", "r") as file:
                    existing_data = json.load(file)
                    existing_workers = {worker["Id"]: worker for worker in existing_data["Workers"]}

                # Diccionario temporal para almacenar los trabajadores actualizados
                updated_workers = {}

                for (id, name, rank, unit), group in grouped_autonomia:
                    worker_tasks = entrenamiento_df_filtered[entrenamiento_df_filtered['Nombre'] == name]
                    skills = []
                    for cargo in group['Cargo'].unique():
                        cargo_tasks = worker_tasks[worker_tasks['Cargo'] == cargo]
                        tasks = [{"TaskCode": row['Codigo Tarea'], "Validity": row['Fecha Vence'].strftime('%Y-%m-%d')} for _, row in cargo_tasks.iterrows()]
                        validity_date = group.loc[group['Cargo'] == cargo, 'Fecha fin'].max().strftime('%Y-%m-%d')
                        skills.append({"Skill": cargo, "Validity": validity_date, "Tasks": tasks})

                    # Conservar las etiquetas existentes o asignar etiquetas vacías
                    tags = existing_workers[int(id)]["Tags"] if int(id) in existing_workers and "Tags" in existing_workers[int(id)] else []

                    # Agregar o actualizar la información del trabajador en el diccionario temporal
                    updated_workers[int(id)] = {"Id": int(id), "Name": name, "Rank": rank, "Unit": unit, "Skills": skills, "Tags": tags}

                # Reemplazar la lista de trabajadores en workers_data con los trabajadores actualizados
                workers_data = {"Workers": list(updated_workers.values())}

                # Guardar la estructura en el archivo JSON
                with open("workers.json", "w") as file:
                    json.dump(workers_data, file, ensure_ascii=False, indent=4)
                QtWidgets.QMessageBox.information(self, "Actualización Exitosa", "El archivo workers.json ha sido actualizado con éxito.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Se produjo un error al actualizar el archivo: {e}")
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Debes seleccionar ambos archivos.")
 

    def initialize_calendar(self):

        #self.calendario.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)   # O SingleSelection, RowSelection, etc.
        self.calendario.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)  # O SelectRows, etc.

        #"""Inicializa el QTableWidget para tener una fila por trabajador y 32 columnas."""
        #with open("workers.json", "r") as file:
        #    data = json.load(file)
        #    self.trabajadores = data["Workers"]

        self.calendario.setRowCount(len(self.trabajadores))
        self.calendario.setColumnCount(32)

    def cell_clicked(self, row, column):

        item = self.calendario.item(row, column)
        if item:
            validity_indicator = item.text()
        else:
            validity_indicator = ""

        # Solo actúa en las columnas que contiene las cadenas de texto VA y VM que corresponden a la fecha de vencimiento de autonomia y maniobras respectivamente
        if validity_indicator == "VA" or validity_indicator == "VM":
            worker = self.trabajadores[row]
            date_str = f"{self.yearComboBox.currentText()}-{self.monthComboBox.currentIndex() + 1:02d}-{column:02d}"
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d")            
            detail = self.find_skill_or_task_by_date(worker, date, validity_indicator)
            QtWidgets.QMessageBox.information(self, "Validez", detail)

    def find_skill_or_task_by_date(self, worker, date, validity_indicator):
        for skill in worker["Skills"]:
            # Convertir la fecha de validez de habilidad a objeto datetime para comparar
            skill_validity = datetime.datetime.strptime(skill["Validity"], "%Y-%m-%d")
            if skill_validity == date and validity_indicator == "VA":
                # Retornar la información de la habilidad si la fecha coincide y el indicador es VA
                return f"Habilidad: {skill['Skill']}\nFin validez: {skill['Validity']}"

            # Verificar si hay tareas dentro de la habilidad que coincidan con la fecha y el indicador
            for task in skill.get("Tasks", []):
                task_validity = datetime.datetime.strptime(task["Validity"], "%Y-%m-%d")
                if task_validity == date and validity_indicator == "VM":
                    # Retornar la información de la tarea si la fecha coincide y el indicador es VM
                    return f"Maniobra: {task['TaskCode']}\nFin validez: {task['Validity']}"

        # Si no hay coincidencias, retornar un mensaje predeterminado
        return "No skill or task found for this date."



    def update_calendar(self):
        """actualiza el calendario para un año y mes específicos."""
        month = self.monthComboBox.currentIndex() + 1
        year = int(self.yearComboBox.currentText())
        last_day = calendar.monthrange(year, month)[1]

        # Elimina las columnas de días
        for _ in range(1, 32):  # Asumimos que siempre hay hasta 31 columnas
            self.calendario.removeColumn(1)

        # Añade las columnas necesarias para el mes seleccionado
        for day in range(1, last_day + 1):
            self.calendario.insertColumn(day)
            date = datetime.date(year, month, day)
            if date.weekday() == 5 or date.weekday() == 6:  # Sábado o domingo
                for row in range(self.calendario.rowCount()):
                    cell = QtWidgets.QTableWidgetItem()
                    cell.setBackground(QtGui.QColor('#f0f0f0'))  # Color gris claro
                    self.calendario.setItem(row, day, cell)


        # Asegúrate de ajustar las cabeceras y las celdas nuevamente
        encabezados = ["Nombre"] + [str(i) for i in range(1, last_day + 1)]
        self.calendario.setHorizontalHeaderLabels(encabezados)

        # Definir el orden deseado para los rangos en una lista
        orden_rank = ["CR", "TC", "MY", "CT", "TE", "ST", "TJ", "TS", "T1", "T2", "T3", "T4", "AT"]

        # Crear un diccionario que asocie cada rango con un valor numérico basado en orden_rank
        orden_dict = {rango: i for i, rango in enumerate(orden_rank)}

        # Ordenar la lista de trabajadores por rango y luego alfabéticamente por nombre
        self.trabajadores = sorted(self.trabajadores, key=lambda x: (orden_dict.get(x["Rank"], float("inf")), x["Name"]))

        # Llama a load_agenda con el mes y año seleccionados
        self.load_agenda(year, month)

        self.calendario.resizeColumnsToContents()
        self.calendario.resizeRowsToContents()
        

    def load_agenda(self, year, month):
        """Carga la agenda para un año y mes específicos."""           
        # Cargar datos de agenda (esto se moverá fuera de esta función si es constante y se llamará solo una vez)
        agenda = {}
        unique_activities = set()
        with open("agenda.csv", "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Considera solo las entradas del mes y año específicos que no hayan sido denegadas
                if (int(row["Date"].split("-")[0]) == year and int(row["Date"].split("-")[1]) == month and 
                row["Status"] != "Denied"):
                    if row["Id"] not in agenda:
                        agenda[row["Id"]] = []
                    agenda[row["Id"]].append(row) # Agrega el diccionario completo
                    unique_activities.add(row["Activity"])

        # Generar colores para cada actividad usando seaborn
        self.colors = dict(zip(unique_activities, sns.color_palette("husl", len(unique_activities)).as_hex()))

        for row, trabajador in enumerate(self.trabajadores):
            # Establecer nombres en la primera columna
            item_nombre = QtWidgets.QTableWidgetItem(trabajador["Rank"] +". "+ trabajador["Name"])
            self.calendario.setItem(row, 0, item_nombre)
            
            idstring = str(trabajador["Id"]) # convierto a cadena el id en trabajadores para poderlo comparar

            if idstring in agenda:
                for entry in agenda[idstring]:
                    # Convertir la fecha (formato YYYY-MM-DD) a día del mes
                    day = int(entry["Date"].split("-")[2])
                    cell = QtWidgets.QTableWidgetItem(entry["Activity"])
                    # Cambiar el color si está 'Pending'
                    if entry["Status"] == "Pending":
                        cell.setBackground(QtGui.QColor('#f0f0f0'))  # Color gris claro
                        
                    else:
                        if entry["Activity"] in self.colors:
                            cell.setBackground(QtGui.QColor(self.colors[entry["Activity"]]))

                    self.calendario.setItem(row, day, cell)

        self.highlight_validity_dates()
        
    def highlight_validity_dates(self):
        # Establece los colores que deseas utilizar para "VA" y "VM"
        colors = {'VA': QtGui.QColor('#FF0000'), 'VM': QtGui.QColor('#FFFF00')}

        # Supongamos que tienes variables year y month establecidas para la vista actual del calendario
        year = int(self.yearComboBox.currentText())
        month = self.monthComboBox.currentIndex() + 1

        # Itera a través de cada trabajador y sus habilidades y códigos de tarea
        for row, worker in enumerate(self.trabajadores):
            for skill in worker.get("Skills", []):
                skill_date = datetime.datetime.strptime(skill["Validity"], "%Y-%m-%d")
                if skill_date.year == year and skill_date.month == month:
                    # Convertir la fecha de validez al día del mes y asignar el color y texto "VA"
                    day = skill_date.day
                    cell = QtWidgets.QTableWidgetItem("VA")
                    cell.setBackground(colors['VA'])
                    self.calendario.setItem(row, day, cell)
                    
                for task in skill.get("Tasks", []):
                    task_date = datetime.datetime.strptime(task["Validity"], "%Y-%m-%d")
                    if task_date.year == year and task_date.month == month:
                        # Convertir la fecha de validez al día del mes y asignar el color y texto "VM"
                        day = task_date.day
                        cell = QtWidgets.QTableWidgetItem("VM")
                        cell.setBackground(colors['VM'])
                        self.calendario.setItem(row, day, cell)
    
    def is_column_fully_selected(self, column):
        # Obtener todos los rangos de selección.
        selection_ranges = self.calendario.selectedRanges()

        # Comprobar si hay algún rango de selección que incluya completamente la columna.
        for selection_range in selection_ranges:
            if (selection_range.leftColumn() <= column <= selection_range.rightColumn() and
                    selection_range.topRow() == 0 and
                    selection_range.bottomRow() == self.calendario.rowCount() - 1):
                return True  # La columna está completamente dentro de un rango de selección y todos las filas están incluidas.

        return False  # Si llegamos aquí, la columna no está completamente seleccionada.

    
    def contextMenuEvent(self, event):
        self.calendario.viewport().updateGeometry()  # Actualiza la geometría
        index = self.calendario.indexAt(event.pos())
        #if not index.isValid():
        #    return  # No hacer nada si el índice no es válido

        #columna = index.column()

        row = self.calendario.currentRow()
        columna = self.calendario.currentColumn()

        if columna == -1 or row == -1:  # Comprobar si no hay una fila/columna seleccionada
            return  # Salir si no hay selección
        
        # Caso especial: celdas de la columna 'Nombre'
        if columna == 0 and self.is_column_fully_selected(columna):
            context_menu = QtWidgets.QMenu(self)
            filter_action = QtWidgets.QAction("FILTRO", self)
            filter_action.triggered.connect(self.show_filter_dialog)
            context_menu.addAction(filter_action)

            # Acción para "Estadística"
            stats_action = QtWidgets.QAction("ESTADÍSTICA", self)
            stats_action.triggered.connect(lambda: self.show_stats_graph())
            context_menu.addAction(stats_action)

            context_menu.exec_(self.mapToGlobal(event.pos()))
            return
#-----------------------------Caso selección nombre de trabajador-------------
        elif columna == 0:  # Verifica si el clic fue en la primera columna
            #row = self.calendario.currentRow()# Guarda el índice seleccionado para usarlo en la acción del menú
            worker = self.trabajadores[row]  # Obtiene el trabajador en la fila seleccionada
            
            context_menu = QtWidgets.QMenu(self)
            
            # Acción "Info"
            info_action = QtWidgets.QAction("INFO", self)
            info_action.triggered.connect(lambda: self.show_worker_stats_form(worker))  # Conecta la acción con la función
            context_menu.addAction(info_action)

        elif columna > 0 and self.is_column_fully_selected(columna):  
            context_menu = QtWidgets.QMenu(self)
            parte_action = QtWidgets.QAction("PARTE", self)
            parte_action.triggered.connect(self.show_parte_dialog)
            context_menu.addAction(parte_action)
            context_menu.exec_(self.mapToGlobal(event.pos())) 

        else:
            #---------------------------------------
            # caso celdas internas de fechas
            self.temp_selected_indexes = self.calendario.selectedIndexes()
            # Restaurar las celdas seleccionadas antes de abrir el menú
            selection_model = self.calendario.selectionModel()
            for index in self.temp_selected_indexes:
                selection_model.select(index, QtCore.QItemSelectionModel.Select)
            
            context_menu = QtWidgets.QMenu(self)

            # Acciones para añadir skills
            for skill in self.current_worker_skills():
                action = QtWidgets.QAction(skill, self)
                action.triggered.connect(lambda checked, s=skill: self.add_skill_to_agenda(s))
                context_menu.addAction(action)

            # Acción para borrar celda
            delete_action = QtWidgets.QAction("BORRAR", self)
            delete_action.triggered.connect(self.delete_selected_cell)
            context_menu.addAction(delete_action)

            # Opción para aprobar/desaprobar solicitudes
            approve_action = QtWidgets.QAction("APROBAR", self)
            approve_action.triggered.connect(lambda: self.show_approval_dialog(row, columna))
            context_menu.addAction(approve_action)

        context_menu.exec_(self.mapToGlobal(event.pos()))

    def save_tags(self, worker, tags_text):

        try:            
            # Extraer las etiquetas del argumento tags_text
            new_tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]

            # Actualizar o crear la llave "Tags" en el diccionario del trabajador
            worker["Tags"] = new_tags

            # Guardar los cambios en el archivo JSON
            with open("workers.json", "r") as file:
                data = json.load(file)
            
            # Buscar el trabajador en el archivo JSON y actualizar sus etiquetas
            for w in data["Workers"]:
                if w["Id"] == worker["Id"]:
                    w["Tags"] = new_tags
                    break

            # Guardar los datos actualizados
            with open("workers.json", "w") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
            print("Archivo actualizado con éxito.")

        except Exception as e:
            print(f"Error al actualizar el archivo: {e}")

    def show_stats_graph(self):
        selected_month = self.monthComboBox.currentIndex() + 1
        selected_year = int(self.yearComboBox.currentText())
        if not self.stats_graph_dialog:
            self.stats_graph_dialog = StatsGraphDialog(self.trabajadores, selected_month, selected_year, self) 
            self.stats_graph_dialog.daySelected.connect(self.select_day_in_agenda)                                                 
            # Establecer el diálogo como "always on top"
            self.stats_graph_dialog.setWindowFlags(self.stats_graph_dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.stats_graph_dialog.show()

    def show_worker_stats_form(self, worker):
        print(f"Mostrando formulario de estadísticas para: {worker['Name']}")
        # Carga el formulario desde el archivo .ui
        worker_stats_dialog = uic.loadUi('workerDialog.ui')

        # Guarda el trabajador como un atributo del diálogo para poder accesarlo en update_graph
        worker_stats_dialog.worker = worker

        # Configurar el widget del gráfico
        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        graphic_widget = worker_stats_dialog.findChild(QtWidgets.QWidget, 'graphicWidget')  # Asume que existe un QWidget con este nombre
        graphic_layout = QtWidgets.QVBoxLayout(graphic_widget)  # Crea un QVBoxLayout dentro del QWidget
        graphic_layout.addWidget(self.canvas)

        # Establece la información del trabajador en los labels
        worker_stats_dialog.findChild(QtWidgets.QLabel, 'nameLabel').setText("Nombre: "+ worker['Rank'] + ". " + worker['Name'])
        worker_stats_dialog.findChild(QtWidgets.QLabel, 'idLabel').setText("CM: " + str(worker['Id']))
        worker_stats_dialog.findChild(QtWidgets.QLabel, 'unitLabel').setText("Unidad: " + worker['Unit'])

       # Obtener referencia al botón 'saveTagsButton' y al QLineEdit 'tagsLineEdit'
        saveTagsButton = worker_stats_dialog.findChild(QtWidgets.QPushButton, 'saveTagsButton')
        tagsLineEdit = worker_stats_dialog.findChild(QtWidgets.QLineEdit, 'tagsLineEdit')

        # Establecer las etiquetas existentes en el QLineEdit
        current_tags = worker.get("Tags", [])
        tagsLineEdit.setText(", ".join(current_tags))

        # Inicializa el QTreeWidget
        tree_widget = worker_stats_dialog.findChild(QtWidgets.QTreeWidget, 'skillsTreeWidget')
        tree_widget.setHeaderLabels(["Habilidad", "Maniobra", "Fin vigencia"])

        # Llena el árbol con los datos
        for skill in worker["Skills"]:
            # Crear un ítem de árbol para la habilidad
            skill_item = QtWidgets.QTreeWidgetItem([skill["Skill"],"",skill["Validity"]])
            tree_widget.addTopLevelItem(skill_item)

            # Si "Tasks" es una clave en la habilidad y su valor no es None
            if "Tasks" in skill and skill["Tasks"]:
                # Iterar sobre cada tarea y añadir como hijo del ítem de habilidad
                for task in skill["Tasks"]:
                    # Asegúrate de que el 'TaskCode' y 'Validity' estén presentes en el diccionario de la tarea
                    if "TaskCode" in task and "Validity" in task:
                        task_item = QtWidgets.QTreeWidgetItem([
                            "",  # Deja el espacio de habilidad vacío para este hijo
                            task["TaskCode"], 
                            task["Validity"]
                        ])
                        skill_item.addChild(task_item)

        #-----------------pone por defecto el lapso de evaluación de la gráfica en el mes y año seleccionados-----------
                        
            # Obtener el mes y año seleccionados en los QComboBox
            current_month = self.monthComboBox.currentIndex() + 1
            current_year = int(self.yearComboBox.currentText())

            # Establecer endDateEdit como el último día del mes actual
            # Encuentra el primer día del próximo mes, luego resta un día
            if current_month == 12:  # Diciembre es un caso especial
                next_month_first_day = datetime.datetime(current_year + 1, 1, 1)
            else:
                next_month_first_day = datetime.datetime(current_year, current_month + 1, 1)
            
            # Establece la fecha final
            end_date = next_month_first_day - datetime.timedelta(days=1)
            worker_stats_dialog.findChild(QtWidgets.QDateEdit, 'endDateEdit').setDate(end_date)

            # Establecer startDateEdit como el primer día del mes actual
            start_date = datetime.datetime(current_year, current_month, 1)
            worker_stats_dialog.findChild(QtWidgets.QDateEdit, 'startDateEdit').setDate(start_date)

        #------------------------------------------------------------------------------------------------ 
                                
        # Establecer el diálogo como "always on top"
        worker_stats_dialog.setWindowFlags(worker_stats_dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        # Mostrar el diálogo de manera no modal
        worker_stats_dialog.show()

        # Conectar señales de los QDateEdit para actualizar el gráfico
        #worker_stats_dialog.startDateEdit.dateChanged.connect(lambda: self.update_graph(worker_stats_dialog))
        #worker_stats_dialog.endDateEdit.dateChanged.connect(lambda: self.update_graph(worker_stats_dialog))

        # Conectar el botón a la función save_tags
        saveTagsButton.clicked.connect(lambda: self.save_tags(worker, tagsLineEdit.text()))

        # Llama a update_graph para inicializar el gráfico
        self.update_graph(worker_stats_dialog)  

        # Guardar la referencia al diálogo para actualizar la gráfica más tarde
        self.worker_stats_dialog = worker_stats_dialog


    def update_pie_chart(self, month=None):
        # Calcula el total de días posibles para el mes o el año
        total_possible_days = sum(self.days_in_month) * 2 / 3 if month is None else self.days_in_month[month - 1] * 2 / 3

        # Calcula los días programados
        programmed_days = 0
        for start_day, end_day, _ in self.worker_series.get(self.worker["Name"], []):
            if month is None:
                # Suma todos los días programados en el año
                programmed_days += end_day - start_day + 1
            else:
                # Suma solo los días programados en el mes específico
                start_date = datetime.datetime(self.year, 1, 1) + datetime.timedelta(days=start_day - 1)
                end_date = datetime.datetime(self.year, 1, 1) + datetime.timedelta(days=end_day - 1)
                if start_date.month == month or end_date.month == month:
                    # Asegúrate de contar solo los días dentro del mes
                    month_start = datetime.datetime(self.year, month, 1)
                    month_end = datetime.datetime(self.year, month, self.days_in_month[month - 1])
                    programmed_days += max(min(end_date, month_end) - max(start_date, month_start), datetime.timedelta(0)).days + 1

        # Calcula el porcentaje de ocupación
        occupation_percentage = min(programmed_days / total_possible_days, 1) * 100

        # Limpia el área central del gráfico si ya existe un gráfico de torta
        if self.pie_ax:
            self.pie_ax.remove()
            self.pie_ax = None

        # Genera el gráfico de torta en el centro del gráfico polar
        self.pie_ax = self.figure.add_axes([0.31, 0.29, 0.4, 0.4], label="PieChart")
        self.pie_ax.pie([occupation_percentage, 100 - occupation_percentage], colors=['red', 'blue'], startangle=90)
        self.pie_ax.set_aspect('equal')  # Asegura que la torta sea un círculo

        # Añade una etiqueta en el centro del gráfico de torta
        month_label = "Año" if month is None else calendar.month_abbr[month]
        self.pie_ax.text(0, 0.1, month_label, ha='center', va='center', color='white', weight='bold', fontsize=14)
        self.pie_ax.text(0, -0.3, f"{occupation_percentage:.1f}%", ha='center', va='center', color='white', weight='bold', fontsize=14)

        self.canvas.draw()

    def draw_annual_activity_chart(self, year, worker,activities):
        self.figure.clear()  # Limpia la figura actual
        ax = self.figure.add_subplot(111, projection='polar')  # Crea un nuevo subplot con proyección polar
       # Define el número de días en cada mes (considera si es un año bisiesto)
        self.days_in_month = [31, 29 if calendar.isleap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

        self.worker_series = {}  # reinicia para el nuevo trabajador
        self.worker = worker
        self.year = year

        # Calcula los ángulos de cada día
        day_angles = np.linspace(0, 2 * np.pi, 365 + int(calendar.isleap(year)), endpoint=False)

        ax.set_theta_direction(-1)
        ax.set_theta_zero_location('N')

        # Asigna colores a cada actividad
        unique_activities = set(activities.values())
        # Genera una paleta de colores
        all_colors = plt.cm.rainbow(np.linspace(0, 1, len(unique_activities) + 2))  # +2 para tener espacio para eliminar colores

        # Convertir a hexadecimal y eliminar colores cercanos al rojo (#FF0000) y amarillo (#FFFF00)
        filtered_colors = [to_hex(color) for color in all_colors if not np.isclose(color, [1, 0, 0, 1]).all() and not np.isclose(color, [1, 1, 0, 1]).all()]

        # Asignar colores a cada actividad
        activity_colors = dict(zip(unique_activities, filtered_colors))

        
        # Diccionario para almacenar las series de programación para cada trabajador
        self.worker_series = {}
        # Variables para llevar un registro de la última actividad y las fechas de la serie actual
        last_activity = None
        current_series_start = None
        
        # Dibuja el anillo de días con los colores de las actividades
        for day, angle in enumerate(day_angles, start=1):
            color = 'lightgray'  # Color por defecto
            activity = activities.get(day, None)

            # Revisa las autonomías y maniobras del trabajador
            for skill in worker["Skills"]:
                # Convierte la fecha de vencimiento a día del año
                skill_validity_date = datetime.datetime.strptime(skill["Validity"], "%Y-%m-%d")
                if skill_validity_date.year == year and skill_validity_date.timetuple().tm_yday == day:
                    color = 'red'  # Rojo para vencimientos de autonomía

                for task in skill.get("Tasks", []):
                    task_validity_date = datetime.datetime.strptime(task["Validity"], "%Y-%m-%d")
                    if task_validity_date.year == year and task_validity_date.timetuple().tm_yday == day:
                        color = 'yellow'  # Amarillo para vencimientos de maniobras

                if activity:
                    color = activity_colors[activity]

                    # Comprueba si la actividad actual es diferente de la última actividad
                    if activity != last_activity:
                        # Si ya hay una serie en curso, guárdala y comienza una nueva
                        if current_series_start is not None:
                            self.worker_series.setdefault(worker["Name"], []).append((current_series_start, day - 1, last_activity))
                        current_series_start = day

                    # Actualiza la última actividad registrada
                    last_activity = activity

                else:
                    # Finaliza la serie actual si no hay actividad en el día actual
                    if current_series_start is not None:
                        self.worker_series.setdefault(worker["Name"], []).append((current_series_start, day - 1, last_activity))
                        current_series_start = None
                        last_activity = None

                ax.plot([angle, angle], [1, 1.1], color=color, linewidth=3)

        # No olvides finalizar la última serie al final del ciclo
        if current_series_start is not None:
            self.worker_series.setdefault(worker["Name"], []).append((current_series_start, day, last_activity))

        # Dibuja el anillo de días
        for day_angle in day_angles:
            ax.plot([day_angle, day_angle], [1, 1.1], color='gray', linewidth=0.5)
        
        # Dibuja el anillo de meses y las líneas para cada inicio de mes
        month_starts = np.cumsum([0] + self.days_in_month[:-1])
        month_angles = day_angles[month_starts]
        for i, month_start in enumerate(month_starts):
            if i < len(month_starts) - 1:
                month_end = month_starts[i + 1]
            else:
                month_end = 365  # Final del año para diciembre

            # Punto medio del mes
            month_middle = (month_start + month_end) // 2
            month_middle_angle = day_angles[month_middle]

            # Dibuja la línea del inicio del mes
            ax.plot([month_angles[i], month_angles[i]], [1, 1.2], color='black', linewidth=0.5)

            # Etiqueta del mes en el punto medio
            ax.text(month_middle_angle, 1.2, month_names[i], horizontalalignment='center')

        # Obtener el día actual
        now = datetime.datetime.now()
        if now.year == year:  # Asegúrate de que el gráfico se refiere al año actual
            current_day_of_year = (now - datetime.datetime(now.year, 1, 1)).days + 1  # Calcula el día del año
            # Calcular el ángulo correspondiente al día actual
            current_day_angle = 2 * np.pi * (current_day_of_year - 1) / (365 + int(calendar.isleap(year)))
            # Dibuja la línea del día actual
            ax.plot([current_day_angle, current_day_angle], [0.8, 1.3], color='green', linewidth=2, linestyle='--')  # Color verde y línea discontinua
            # Puede agregar un marcador o un texto para indicar que es el día actual
            ax.text(current_day_angle, 1.35, 'Hoy', horizontalalignment='center', color='green')

        def on_hover(event):
            if event.inaxes is not None:
                x, y = event.xdata, event.ydata
                for day_of_year, angle in enumerate(day_angles, start=1):
                    if np.abs(angle - x) < 0.01:
                        # Convertir día del año a fecha y luego a día del mes
                        date_of_year = datetime.datetime(self.year, 1, 1) + datetime.timedelta(days=day_of_year - 1)
                        day_of_month = date_of_year.day

                        # Verificar vencimientos de autonomías y maniobras
                        message = activities.get(day_of_year, "No activity")
                        for skill in self.worker["Skills"]:
                            skill_validity_date = datetime.datetime.strptime(skill["Validity"], "%Y-%m-%d")
                            skill_day_of_year = skill_validity_date.timetuple().tm_yday
                            if skill_validity_date.year == self.year and skill_day_of_year == day_of_year:
                                habilidad = skill["Skill"]
                                message = f"Vencimiento Autonomía {habilidad}"
                            for task in skill.get("Tasks", []):
                                task_validity_date = datetime.datetime.strptime(task["Validity"], "%Y-%m-%d")
                                task_day_of_year = task_validity_date.timetuple().tm_yday
                                if task_validity_date.year == self.year and task_day_of_year == day_of_year:
                                    maniobra = task["TaskCode"]
                                    message = f"Vencimiento Maniobra {maniobra}"

                        # Encuentra las series para el trabajador del día actual
                        for start_day, end_day, activity_name in self.worker_series.get(self.worker["Name"], []):
                            if start_day <= day_of_year <= end_day:
                                start_date = datetime.datetime(self.year, 1, 1) + datetime.timedelta(days=start_day - 1)
                                end_date = datetime.datetime(self.year, 1, 1) + datetime.timedelta(days=end_day - 1)
                                message += f"\nSerie: {activity_name} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"
                                break

                        tooltip = f"Day: {day_of_month}\nActivity: {message}"
                        QtWidgets.QToolTip.showText(event.guiEvent.globalPos(), tooltip)

                        # Actualiza el gráfico de torta para el mes del día actual
                        self.update_pie_chart(month=date_of_year.month)
                        break
                else:
                    # Si no está señalando ningún día, muestra el gráfico de torta del año completo
                    self.update_pie_chart()
                    QtWidgets.QToolTip.hideText()

        self.canvas.mpl_connect('motion_notify_event', on_hover)
        
        self.update_pie_chart()  # Esto mostrará inicialmente el gráfico de torta para el año completo

        ax.set_axis_off()
        self.canvas.draw()



    def update_graph(self, worker_stats_dialog):
                        
        # Comprobar si worker_stats_dialog es None o no está visible
        if not worker_stats_dialog or not worker_stats_dialog.isVisible():
            return  # Salir de la función si no se cumple la condición
       
           # Obtener el año actual
        current_year = datetime.datetime.now().year

        # Obtener el ID del trabajador desde el diálogo
        worker_id = worker_stats_dialog.worker['Id']

        # Leer el archivo de agenda y filtrar por el trabajador y el año actual
        df_agenda = pd.read_csv("agenda.csv", encoding='ISO-8859-1')
        df_agenda['Date'] = pd.to_datetime(df_agenda['Date'])
        df_agenda = df_agenda[(df_agenda['Id'] == worker_id) & (df_agenda['Date'].dt.year == current_year)]

        # Preparar los datos para el gráfico anual
        activities = {}
        for _, row in df_agenda.iterrows():
            day_of_year = row['Date'].timetuple().tm_yday
            activities[day_of_year] = row['Activity']

        # Limpia la figura
        self.figure.clear() 

        # Llamar a la función para dibujar el gráfico anual
        self.draw_annual_activity_chart(current_year, worker_stats_dialog.worker, activities)

    def on_calendar_change(self):
        # Llamado cuando se hace un cambio en self.calendario
        if hasattr(self, 'worker_stats_dialog'):
            self.update_graph(self.worker_stats_dialog)
     
    
    def current_worker_skills(self):
        row = self.calendario.currentRow()
        worker = self.trabajadores[row]
        skill_names = [skill["Skill"] for skill in worker["Skills"]]
        return skill_names

    def add_skill_to_agenda(self, skill):
        for index in self.temp_selected_indexes:
            row = index.row()
            column = index.column()

            if row == -1 or column == 0:  # Ignorar si no hay fila seleccionada o si es la columna de nombres
                continue

            worker = self.trabajadores[row]
            worker_id = worker["Id"]
            worker_name = worker["Name"]            
            date = f"{self.yearComboBox.currentText()}-{self.monthComboBox.currentIndex() + 1:02d}-{column:02d}"
            worker_rank = worker["Rank"]
            activity = skill  # Suponiendo que 'skill' es el nombre de la actividad

            # Antes de añadir la habilidad a la agenda, comprobar el horario del trabajador
            if self.check_worker_schedule(worker_id, worker_name):

                # Campos adicionales
                status = "Pending"  # Por defecto, el estado es 'Pending'
                requested_by = self.username  # Suponiendo que tienes un atributo para el usuario actual
                request_date = datetime.datetime.now().strftime('%Y-%m-%d')
                approve_by = ""
                approve_date = ""
                # Formato de texto plano para el historial
                history = json.dumps([{"date": request_date, "action": "requested", "by": requested_by}])

                # Añadir la entrada a la agenda
                with open("agenda.csv", "a", newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([worker_id, date, activity, worker_rank, worker_name, requested_by, request_date, approve_by, approve_date, status, history])
            else:
                # No hacer nada si las comprobaciones no son satisfactorias
                continue
        # Actualizar el calendario
        self.update_calendar()

        # Actualizar el gráfico si worker_stats_dialog está abierto
        if hasattr(self, 'worker_stats_dialog'):
            self.update_graph(self.worker_stats_dialog)

    def delete_selected_cell(self):
        """Borra la celda seleccionada."""
        for index in self.temp_selected_indexes:
            row = index.row()
            day = index.column()

            if day == 0:  # Ignorar la columna de nombres
                continue

            worker_id = self.trabajadores[row]["Id"]
            idstring = str(worker_id)
            date = f"{self.yearComboBox.currentText()}-{self.monthComboBox.currentIndex() + 1:02d}-{day:02d}"

            # Eliminar la entrada en el archivo 'agenda.csv'
            self.remove_entry_from_agenda(idstring, date)

        # Actualizar el calendario
        self.update_calendar()

        # Actualizar el gráfico si worker_stats_dialog está abierto
        if hasattr(self, 'worker_stats_dialog'):
            self.update_graph(self.worker_stats_dialog)

    def remove_entry_from_agenda(self, worker_id, date):
        """Función auxiliar para borrar una entrada de 'agenda.csv'."""
        rows = []
        with open("agenda.csv", "r") as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] != worker_id or row[1] != date:
                    rows.append(row)

        with open("agenda.csv", "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerows(rows)

    def show_parte_dialog(self):
        print("Parte")

    def show_filter_dialog(self):

        active_units = {worker['Unit'] for worker in self.trabajadores}
        
        active_cargos = set()
        for worker in self.trabajadores:
            for skill in worker['Skills']:
                active_cargos.add(skill['Skill'])

        # Obtener todas las etiquetas únicas
        all_tags = set()
        for worker in self.trabajadores:
            if "Tags" in worker:
                all_tags.update(worker["Tags"])

        # Mostrar el diálogo de filtro con etiquetas
        self.dialog = FilterDialog(active_units, active_cargos, all_tags, self)
        self.dialog.filtersApplied.connect(self.display_filtered_workers)
        self.dialog.exec_()

    def display_filtered_workers(self, selected_units, selected_cargos, selected_tags):

        # cargo toda la base de datos para posterior filtarla de acuerdo a la selección
        with open("workers.json", "r") as file:
            data = json.load(file)
            self.trabajadores = data["Workers"]


        # Filtra los trabajadores por unidad y cargo seleccionados
        filtered_workers = [worker for worker in self.trabajadores
                            if worker["Unit"] in selected_units and 
                            any(skill["Skill"] in selected_cargos for skill in worker["Skills"])]
        
           # Si hay etiquetas seleccionadas, aplica el filtro de etiquetas
        if selected_tags:
            filtered_workers = [worker for worker in filtered_workers
                                if set(worker.get("Tags", [])) & selected_tags]

        # Asigna el conjunto filtrado a trabajadores y actualiza el calendario
        self.calendario.clearContents()
        self.calendario.setRowCount(len(filtered_workers))
        self.trabajadores = filtered_workers  # Ahora trabajadores contiene solo los trabajadores filtrados
        self.update_calendar()  # Llama a load_agenda para actualizar la vista con los trabajadores filtrados

    def check_worker_schedule(self, worker_id, worker_name):
        # Convertir worker_id a cadena de texto para la comparación
        worker_id_str = str(worker_id)

        # Obtén el mes y año actuales desde los QComboBox
        month = self.monthComboBox.currentIndex() + 1
        year = int(self.yearComboBox.currentText())

        # Carga la agenda del trabajador para el mes y año seleccionados
        dates_programmed = []
        with open("agenda.csv", "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Id"] == worker_id_str and int(row["Date"].split("-")[0]) == year and int(row["Date"].split("-")[1]) == month:
                    dates_programmed.append(datetime.datetime.strptime(row["Date"], "%Y-%m-%d"))

        print(f"Trabajador: {worker_name} (ID: {worker_id})")
        print("Fechas programadas:", [date.strftime("%Y-%m-%d") for date in dates_programmed])
        print("Número de dias:", len(dates_programmed))

        # Comprobación dias discontinuos
        if len(dates_programmed) >= 20:
            print(f"Programado más de 20 días: {len(dates_programmed)} días")
            reply = QtWidgets.QMessageBox.question(self, "Confirmar Cambio",
                                                f"El trabajador {worker_name} ya ha sido programado 20 días en el mes. ¿Desea continuar?",
                                                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply == QtWidgets.QMessageBox.Cancel:
                return False

        # Comprobación dias continuos
        if self.is_programmed_continuous(dates_programmed, 14):
            reply = QtWidgets.QMessageBox.question(self, "Confirmar Cambio",
                                                   f"El trabajador {worker_name} ha sido programado más de 14 días continuos. ¿Desea continuar?",
                                                   QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply == QtWidgets.QMessageBox.Cancel:
                return False

        # Comprobación fines de semana
        if not self.has_free_weekend(dates_programmed):
            reply = QtWidgets.QMessageBox.question(self, "Confirmar Cambio",
                                                   f"El trabajador {worker_name} no tiene al menos un fin de semana libre. ¿Desea continuar?",
                                                   QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply == QtWidgets.QMessageBox.Cancel:
                return False

        return True

    def is_programmed_continuous(self, dates, days):
        for i in range(len(dates) - days + 1):
            if all((dates[i + j] - dates[i]).days == j for j in range(days)):
                return True
        return False

    def has_free_weekend(self, dates_programmed):
        # Crear un conjunto de todos los sábados y domingos del mes
        month = self.monthComboBox.currentIndex() + 1
        year = int(self.yearComboBox.currentText())
        all_weekends = set()
        for i in range(1, calendar.monthrange(year, month)[1] + 1):
            date = datetime.date(year, month, i)
            if date.weekday() >= 5:  # Sábado o domingo
                all_weekends.add(date)

        # Crear un conjunto de los fines de semana programados
        programmed_weekends = set(date for date in dates_programmed if date.weekday() >= 5)

        # Verificar si hay al menos un fin de semana no programado
        return not all_weekends.issubset(programmed_weekends)

    def get_worker_name_by_id(self, worker_id):
        for worker in self.trabajadores:
            if worker['Id'] == worker_id:
                return worker['Name']
        return "Desconocido"  # En caso de que el ID no coincida con ningún trabajador
    

    def show_approval_dialog(self, row = None, column=None, worker_id=None, date=None):
        if worker_id is None and date is None:
            # Llamada desde el calendario
            worker_id = str(self.trabajadores[row]["Id"]).strip()
            date = f"{self.yearComboBox.currentText()}-{self.monthComboBox.currentIndex() + 1:02d}-{column:02d}".strip()
            print(f"Buscando ID: {worker_id}, Fecha: {date}")
        else:
            # Esto significa que se han proporcionado worker_id y date
            worker_id = str(worker_id).strip()
            date = str(date).strip()
            print(f"Buscando directamente: ID: {worker_id}, Fecha: {date}")

        history = None
        status = None  # Almacena el estado de la solicitud
        
        with open("agenda.csv", "r", encoding='ISO-8859-1') as file:  # Usa 'latin-1' o 'cp1252' si sospechas que el archivo puede estar en esa codificación
            reader = csv.DictReader(file)

            for entry in reader:
                csv_id = entry["Id"].strip()  # Eliminar espacios
                csv_date = entry["Date"].strip()  # Eliminar espacios
                print(f"CSV Entry - ID: {csv_id}, Fecha: {csv_date}")  # Imprimir cada entrada del CSV
                if str(csv_id) == str(worker_id) and str(csv_date) == str(date):
                    history = entry["History"]
                    status = entry["Status"]  # Obtener el estado de la solicitud
                    print(history)
                    break

        # Crear y mostrar el diálogo de aprobación
        dialog = ApprovalDialog(self, worker_id, date)  # Pasar worker_id y date

        if history:
            try:
                history_json = json.loads(history)
                formatted_history = "\n".join(
                    [f"{entry['date']}: {entry['action']} by {entry['by']}" +
                     (f", comment: {entry['comments']}" if 'comments' in entry else '')
                     for entry in history_json])
                dialog.set_history(formatted_history)
            except json.JSONDecodeError:
                dialog.set_history("Historial no disponible o corrupto")
        else:
            print("No se encontró la entrada correspondiente en el archivo CSV.")

        # Establece el estado de la solicitud en el diálogo
        if status:
            dialog.set_status(status)
        else:
            dialog.set_status("Desconocido")

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Implementar la lógica para actualizar la solicitud aquí
            pass

    def update_approval(self, worker_id, date, status, comments):
        # Leer y actualizar el archivo CSV
        updated_rows = []
        with open("agenda.csv", "r", encoding='ISO-8859-1') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Id"] == worker_id and row["Date"] == date:
                    # Actualiza el estado y añade el comentario al historial
                    row["Status"] = status
                    history = json.loads(row["History"])                    
                    history.append({"date": datetime.datetime.now().strftime('%Y-%m-%d'), "action": status, "by": self.username, "comments": comments})
                    row["History"] = json.dumps(history)
                updated_rows.append(row)
        self.update_calendar()

        # Sobrescribe el archivo CSV con los datos actualizados
        with open("agenda.csv", "w", newline='', encoding='ISO-8859-1') as file:
            writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)

        # Actualizar la visualización en el calendario
        self.update_calendar()
        # Si el diálogo de solicitudes está abierto, actualízalo
        if self.request_dialog:
            self.request_dialog.load_requests()

        # Actualizar el gráfico si el diálogo de estadísticas está abierto
        if self.worker_stats_dialog:
            self.update_graph(self.worker_stats_dialog)     
        
        # Actualizar el gráfico si el diálogo de estadísticas está abierto
        if self.stats_graph_dialog and self.stats_graph_dialog.isVisible():
            self.stats_graph_dialog.update_graph()
            self.stats_graph_dialog.update_continuity_graph()



    def update_series(self, worker_id, date, status, comments):
        # Leer todas las filas del archivo CSV
        with open("agenda.csv", "r", encoding='ISO-8859-1') as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Ordenar las filas primero por ID y luego por fecha
        rows.sort(key=lambda row: (row['Id'], row['Date']))

        # Encontrar índice de la fila con la fecha seleccionada
        selected_index = next((i for i, row in enumerate(rows) if row["Id"] == worker_id and row["Date"] == date), None)
        if selected_index is None:
            return  # No se encontró la fila seleccionada

        # Actualizar la fila seleccionada y las adyacentes si son continuas
        self.update_row(rows[selected_index], status, comments)
        self.update_continuous_rows(rows, selected_index, worker_id, status, comments)

        # Sobrescribir el archivo CSV con las filas actualizadas
        with open("agenda.csv", "w", newline='', encoding='ISO-8859-1') as file:
            writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Actualizar gráficos y visualizaciones
        self.update_calendar()
        if self.stats_graph_dialog and self.stats_graph_dialog.isVisible():
            self.stats_graph_dialog.update_graph()
            self.stats_graph_dialog.update_continuity_graph()

    def update_continuous_rows(self, rows, selected_index, worker_id, status, comments):
        # Actualizar filas anteriores si son continuas
        i = selected_index - 1
        while i >= 0 and rows[i]["Id"] == worker_id and self.is_continuous(rows[i]["Date"], rows[i + 1]["Date"]):
            self.update_row(rows[i], status, comments)
            i -= 1

        # Actualizar filas posteriores si son continuas
        i = selected_index + 1
        while i < len(rows) and rows[i]["Id"] == worker_id and self.is_continuous(rows[i - 1]["Date"], rows[i]["Date"]):
            self.update_row(rows[i], status, comments)
            i += 1

    def update_row(self, row, status, comments):
        row["Status"] = status
        history = json.loads(row["History"])
        history.append({"date": datetime.datetime.now().strftime('%Y-%m-%d'), "action": status, "by": self.username, "comments": comments})
        row["History"] = json.dumps(history)

    def is_continuous(self, date1, date2):
        # Convierte las fechas a objetos datetime y comprueba si son continuas
        date1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
        date2 = datetime.datetime.strptime(date2, "%Y-%m-%d")
        return (date2 - date1).days == 1
    
#---------------------------------Clase para el Dialogo de filtro------------------------------------

class FilterDialog(QDialog):
    # Crea una señal personalizada que enviará un set de unidades y cargos seleccionados
    filtersApplied = pyqtSignal(set, set, set)

    def __init__(self, active_units, active_cargos, all_tags, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtro")

        # Layout principal del diálogo
        layout = QHBoxLayout()

        # Leer el archivo JSON
        with open('workers.json', 'r') as file:
            workers_data = json.load(file)

        # Extraer valores únicos para unidades y cargos
        self.unidades_set = set()
        self.cargos_set = set()
        for worker in workers_data["Workers"]:
            self.unidades_set.add(worker["Unit"])
            for skill in worker["Skills"]:
                self.cargos_set.add(skill["Skill"])

        # Convertir conjuntos a listas y ordenarlas
        self.unidades_unicas = sorted(list(self.unidades_set))
        self.cargos_unicos = sorted(list(self.cargos_set))

        # Sección para etiquetas
        self.tag_group = QGroupBox("Etiquetas")
        self.tag_layout = QVBoxLayout()

        self.tag_checkboxes = {}
        for tag in all_tags:
            chk = QCheckBox(tag)
            self.tag_layout.addWidget(chk)
            self.tag_checkboxes[tag] = chk

        self.tag_group.setLayout(self.tag_layout)
        layout.addWidget(self.tag_group)

        # Grupo de checkboxes para "Unidad"
        self.unidad_group = QGroupBox("Unidad")
        self.unidad_layout = QVBoxLayout()

        # Añadir checkboxes basados en unidades únicas
        self.unidad_checkboxes = {}
        for unidad in self.unidades_unicas:
            chk = QCheckBox(unidad)
            self.unidad_layout.addWidget(chk)
            self.unidad_checkboxes[unidad] = chk  # Almacenar referencia al checkbox

        self.unidad_group.setLayout(self.unidad_layout)
        layout.addWidget(self.unidad_group)

        # Grupo de checkboxes para "Cargo"
        self.cargo_group = QGroupBox("Cargo")
        self.cargo_layout = QVBoxLayout()

        self.cargo_checkboxes = {}
        # Añadir checkboxes basados en cargos únicos
        for cargo in self.cargos_unicos:
            chk = QCheckBox(cargo)
            self.cargo_layout.addWidget(chk)
            self.cargo_checkboxes[cargo] = chk  # Almacenar referencia al checkbox


        # Ajustar el estado de los checkboxes de acuerdo a las unidades y cargos activos
        for unidad in self.unidad_checkboxes:
            self.unidad_checkboxes[unidad].setChecked(unidad in active_units)
        for cargo in self.cargo_checkboxes:
            self.cargo_checkboxes[cargo].setChecked(cargo in active_cargos)
            

        self.cargo_group.setLayout(self.cargo_layout)
        layout.addWidget(self.cargo_group)


        # Sección para los botones
        button_section = QGroupBox("Acciones")  # Puedes usar QGroupBox si quieres un borde alrededor
        button_layout = QVBoxLayout(button_section)
        
        # Botón para seleccionar/deseleccionar todos los checkboxes
        self.toggle_all_button = QPushButton("Seleccionar/Deseleccionar Todo", self)
        self.toggle_all_button.clicked.connect(self.toggle_all_checkboxes)
        button_layout.addWidget(self.toggle_all_button)

        # Botón para aplicar el filtro
        self.apply_button = QPushButton("Aplicar", self)
        self.apply_button.clicked.connect(self.apply_filters)
        button_layout.addWidget(self.apply_button)

        # Añadir la sección de botones al layout principal
        layout.addWidget(button_section)

        self.setLayout(layout)
    
    def toggle_all_checkboxes(self):
        # Comprueba si hay al menos un checkbox no seleccionado en ambos grupos
        is_any_unchecked = any(not chk.isChecked() for chk in self.unidad_checkboxes.values()) or \
                           any(not chk.isChecked() for chk in self.cargo_checkboxes.values())

        # Establece el estado de todos los checkboxes
        for chk in self.unidad_checkboxes.values():
            chk.setChecked(is_any_unchecked)
        for chk in self.cargo_checkboxes.values():
            chk.setChecked(is_any_unchecked)

    def apply_filters(self):
        selected_units = {chk.text() for chk in self.findChildren(QCheckBox) if chk.isChecked() and chk.parent() == self.unidad_group}
        selected_cargos = {chk.text() for chk in self.findChildren(QCheckBox) if chk.isChecked() and chk.parent() == self.cargo_group}
        selected_tags = {chk.text() for chk in self.findChildren(QCheckBox) if chk.isChecked() and chk.parent() == self.tag_group}
        self.filtersApplied.emit(selected_units, selected_cargos, selected_tags)
        self.accept()
#---------------------------------Clase para el Dialogo de Login------------------------------------

class LoginDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Inicio de Sesión")
        self.setFixedSize(600, 200)

        layout = QtWidgets.QVBoxLayout()

        # Campos de usuario y contraseña
        self.username_field = QtWidgets.QLineEdit(self)
        self.password_field = QtWidgets.QLineEdit(self)
        self.password_field.setEchoMode(QtWidgets.QLineEdit.Password)

        # Botón de inicio de sesión
        login_button = QtWidgets.QPushButton('Iniciar Sesión', self)
        login_button.clicked.connect(self.attempt_login)

        # Añadir widgets al layout
        layout.addWidget(QtWidgets.QLabel("Usuario:"))
        layout.addWidget(self.username_field)
        layout.addWidget(QtWidgets.QLabel("Contraseña:"))
        layout.addWidget(self.password_field)
        layout.addWidget(login_button)

        self.setLayout(layout)

    def attempt_login(self):
        username = self.username_field.text()
        password = self.password_field.text()

        if username == password:  # Reemplaza esta línea con tu lógica de validación
            self.username = username  # Almacena el nombre de usuario
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Nombre de usuario o contraseña incorrecta.")


#---------------------------------Clase para el Dialogo de Aprobación de solicitudes------------------------------------

class ApprovalDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, worker_id=None, date=None):
        super().__init__(parent)
        self.worker_id = worker_id
        self.date = date

        self.setWindowTitle("Aprobación de Solicitud")
        self.setFixedSize(600, 400)

        # Layout y widgets para el diálogo
        layout = QtWidgets.QVBoxLayout(self)

        # Agregar label para el estado de la solicitud
        self.statusLabel = QtWidgets.QLabel("Estado de la Solicitud: [Estado Aquí]")
        layout.addWidget(self.statusLabel)

        # Agregar historial
        self.historyTextEdit = QtWidgets.QTextEdit()
        self.historyTextEdit.setReadOnly(True)  # Solo lectura
        layout.addWidget(self.historyTextEdit)
  
        # Agregar campo para comentarios
        self.commentsTextEdit = QtWidgets.QTextEdit()
        self.commentsTextEdit.setPlaceholderText("Ingrese sus comentarios aquí...")
        layout.addWidget(self.commentsTextEdit)

        # Botones para aprobar y desaprobar
        approveButton = QtWidgets.QPushButton("Aprobar", self)
        approveButton.clicked.connect(self.approve)
        layout.addWidget(approveButton)

        # Botones para aprobar y desaprobar serie
        approveSeriesButton = QtWidgets.QPushButton("Aprobar Serie", self)
        approveSeriesButton.clicked.connect(self.approve_series)
        layout.addWidget(approveSeriesButton)

        disapproveButton = QtWidgets.QPushButton("Desaprobar", self)
        disapproveButton.clicked.connect(self.disapprove)
        layout.addWidget(disapproveButton)

        disapproveSeriesButton = QtWidgets.QPushButton("Desaprobar Serie", self)
        disapproveSeriesButton.clicked.connect(self.disapprove_series)
        layout.addWidget(disapproveSeriesButton)

        # Configura el layout
        self.setLayout(layout)

        # Configurar el diálogo como modal
        self.setModal(True)

    def set_history(self, history):
        self.historyTextEdit.setText(history)

    def set_status(self, status):
        self.statusLabel.setText(f"Estado de la Solicitud: {status}")

    def get_comments(self):
        return self.commentsTextEdit.toPlainText()

    def approve(self):
        # Captura los comentarios
        comments = self.get_comments()
        # Pasa el estado "Approved" y los comentarios a la ventana principal para actualizar
        self.parent().update_approval(self.worker_id, self.date, "Approved", comments)
        self.accept()

    def disapprove(self):
        # Captura los comentarios
        comments = self.get_comments()
        # Pasa el estado "Denied" y los comentarios a la ventana principal para actualizar
        self.parent().update_approval(self.worker_id, self.date, "Denied", comments)
        self.accept()

    def approve_series(self):
        comments = self.get_comments()
        self.parent().update_series(self.worker_id, self.date, "Approved", comments)
        self.accept()

    def disapprove_series(self):
        comments = self.get_comments()
        self.parent().update_series(self.worker_id, self.date, "Denied", comments)
        self.accept()

#---------------------------------Clase para el Dialogo de visualización de solicitudes------------------------------------

class RequestDialog(QtWidgets.QDialog):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app  # Guardar la referencia a la instancia de MiApp

        self.setWindowTitle("Solicitudes")
        self.resize(900, 400)

        # Crear un QTableWidget
        self.tableWidget = QtWidgets.QTableWidget(self)
        self.tableWidget.setColumnCount(6)
        self.tableWidget.setHorizontalHeaderLabels(['Fecha', 'Grado', 'Nombre', 'Id', 'Solicitante', 'Estado'])
        self.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # conecto la acción click en la tabla con la función que llama a aproval dialog
        self.tableWidget.cellClicked.connect(self.on_table_cell_clicked)

        # Layout
        layout = QtWidgets.QVBoxLayout(self)

        # Crear checkboxes para filtrar
        self.checkbox_layout = QtWidgets.QHBoxLayout()
        self.pending_checkbox = QtWidgets.QCheckBox("Pendiente")
        self.accepted_checkbox = QtWidgets.QCheckBox("Aceptada")
        self.denied_checkbox = QtWidgets.QCheckBox("Denegada")

        # Inicializar los checkboxes como marcados
        self.pending_checkbox.setChecked(True)
        self.accepted_checkbox.setChecked(True)
        self.denied_checkbox.setChecked(True)

        # Añadir checkboxes al layout
        self.checkbox_layout.addWidget(self.pending_checkbox)
        self.checkbox_layout.addWidget(self.accepted_checkbox)
        self.checkbox_layout.addWidget(self.denied_checkbox)

        layout.addLayout(self.checkbox_layout)

        # Conectar cambios en los checkboxes con el método de actualización
        self.pending_checkbox.stateChanged.connect(self.load_requests)
        self.accepted_checkbox.stateChanged.connect(self.load_requests)
        self.denied_checkbox.stateChanged.connect(self.load_requests)

        #tabla
        layout.addWidget(self.tableWidget)
        self.setLayout(layout)

        # Poblar la tabla (esto se hará con datos reales)
        self.load_requests()

        # Conectar el evento de clic en una fila
        self.tableWidget.cellClicked.connect(self.on_table_cell_clicked)

    def load_requests(self):
        # Primero, limpia cualquier contenido existente en la tabla
        self.tableWidget.setRowCount(0)

        # Desconectar la señal cellClicked para evitar conexiones múltiples
        # Asegúrate de usar try-except para manejar el caso en que la señal no esté conectada
        try:
            self.tableWidget.cellClicked.disconnect(self.on_table_cell_clicked)
        except TypeError:
            pass  # No hay conexión existente

        # Lee el archivo CSV
        with open("agenda.csv", "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Comprobar los estados y mostrar solo los seleccionados
                if ((self.pending_checkbox.isChecked() and row['Status'] == 'Pending') or
                    (self.accepted_checkbox.isChecked() and row['Status'] == 'Approved') or
                    (self.denied_checkbox.isChecked() and row['Status'] == 'Denied')):
                    
                    # Añade una fila por cada solicitud filtrada
                    current_row = self.tableWidget.rowCount()
                    self.tableWidget.insertRow(current_row)

                    # Añadir los datos de la solicitud en cada celda
                    self.tableWidget.setItem(current_row, 0, QtWidgets.QTableWidgetItem(row['Date']))
                    self.tableWidget.setItem(current_row, 1, QtWidgets.QTableWidgetItem(row['Rank']))
                    self.tableWidget.setItem(current_row, 2, QtWidgets.QTableWidgetItem(row['Name']))
                    self.tableWidget.setItem(current_row, 3, QtWidgets.QTableWidgetItem(row['Id']))
                    self.tableWidget.setItem(current_row, 4, QtWidgets.QTableWidgetItem(row['RequestedBy']))
                    self.tableWidget.setItem(current_row, 5, QtWidgets.QTableWidgetItem(row['Status']))

                    # Añadir los datos de la solicitud en cada celda y modificar el color si es necesario
                    for col_index, col_name in enumerate(['Date', 'Rank', 'Name', 'Id', 'RequestedBy', 'Status']):
                        cell = QtWidgets.QTableWidgetItem(row[col_name])
                        if row['Status'] in ['Approved', 'Denied']:
                            cell.setBackground(QtGui.QColor('#f0f0f0'))  # Color gris claro
                        self.tableWidget.setItem(current_row, col_index, cell)


        # Ajustar el tamaño de las columnas
        self.tableWidget.resizeColumnsToContents()

        # Conectar el evento de clic en una fila
        self.tableWidget.cellClicked.connect(self.on_table_cell_clicked)

    def on_table_cell_clicked(self, row):

        try:
            self.tableWidget.cellClicked.disconnect(self.on_table_cell_clicked)
        except TypeError:
            pass  # No hay conexión existente

        # Obtener los datos de la fila seleccionada
        selected_date = self.tableWidget.item(row, 0).text()
        worker_id = self.tableWidget.item(row, 3).text()

        # Llamar a show_approval_dialog de la instancia de MiApp
        print(worker_id)
        print(selected_date)
        self.main_app.show_approval_dialog(worker_id=worker_id, date=selected_date)

        # Conectar el evento de clic en una fila
        self.tableWidget.cellClicked.connect(self.on_table_cell_clicked)

#-------------Clase de estadísticas-------------------------------------------------
        
class StatsGraphDialog(QtWidgets.QDialog):

    daySelected = pyqtSignal(int)  # Señal para el día seleccionado

    def __init__(self, trabajadores, selected_month, selected_year, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Estadísticas")
        self.resize(800, 600)

        # Almacenar mes y año seleccionados
        self.selected_month = selected_month
        self.selected_year = selected_year
        self.trabajadores = trabajadores

        # Configurar el layout principal
        main_layout = QtWidgets.QVBoxLayout(self)

        # Crear controles para las fechas y agruparlos en un layout horizontal
        date_layout = QtWidgets.QHBoxLayout()
        self.startDateEdit = QtWidgets.QDateEdit(self)
        self.endDateEdit = QtWidgets.QDateEdit(self)
        self.startDateEdit.setCalendarPopup(True)
        self.endDateEdit.setCalendarPopup(True)
        date_layout.addWidget(QtWidgets.QLabel("Fecha Inicio:"))
        date_layout.addWidget(self.startDateEdit)
        date_layout.addWidget(QtWidgets.QLabel("Fecha Fin:"))
        date_layout.addWidget(self.endDateEdit)

        # Añadir el layout de fechas al layout principal
        main_layout.addLayout(date_layout)

        # Crear un QTabWidget para los tabsheets
        self.tabs = QtWidgets.QTabWidget(self)
        
        # Tab para "Frecuencia"
        self.tabFrecuencia = QtWidgets.QWidget()
        self.tabs.addTab(self.tabFrecuencia, "Frecuencia")

        # Configurar el widget del gráfico en el tab "Frecuencia"
        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        frecuencia_layout = QtWidgets.QVBoxLayout(self.tabFrecuencia)
        frecuencia_layout.addWidget(self.canvas)

        # Tab para "Continuidad"
        self.tabContinuidad = QtWidgets.QWidget()
        self.tabs.addTab(self.tabContinuidad, "Continuidad")

        # Layout para el tab de Continuidad
        contLayout = QtWidgets.QVBoxLayout(self.tabContinuidad)


        # QComboBox para seleccionar la actividad
        self.activityComboBox = QtWidgets.QComboBox(self.tabContinuidad)
        contLayout.addWidget(self.activityComboBox)

        # Inicializa el gráfico de continuidad
        self.continuity_figure = plt.figure()
        self.continuity_canvas = FigureCanvas(self.continuity_figure)
        contLayout.addWidget(self.continuity_canvas)

        # Rellenar el QComboBox con actividades
        self.populate_activities()

        # Añadir el QTabWidget al layout principal
        main_layout.addWidget(self.tabs)

        # conectar señal movimiento mouse sobre grafico de continuidad
        self.continuity_canvas.mpl_connect('motion_notify_event', self.on_hover)

        # Conectar el cambio de selección en el QComboBox
        self.activityComboBox.currentIndexChanged.connect(self.update_continuity_graph)

        # Conectar señales de los QDateEdit
        self.startDateEdit.dateChanged.connect(self.update_graph)
        self.endDateEdit.dateChanged.connect(self.update_graph)

        # Establecer fechas por defecto
        self.set_default_dates()

        # Actualizar el gráfico inicialmente
        self.update_graph()

        # Llamada a update_continuity_graph para inicializar el gráfico
        self.update_continuity_graph()

    def on_hover(self, event):
        # Verifica si el evento ocurrió en los ejes del gráfico
        if event.inaxes is not None:
            x, y = event.xdata, event.ydata
            for line in event.inaxes.get_lines():
                x_data = line.get_xdata()
                y_data = line.get_ydata()
                for i in range(len(x_data)):
                    if abs(x - x_data[i]) < 0.5 and abs(y - y_data[i]) < 0.5:  # Ajustar el umbral según sea necesario
                        # El ratón está cerca de este punto
                        day = int(x_data[i])
                        workers = ", ".join(self.workers_per_day.get(day, ["Ninguno"]))
                        tooltip = f"Día: {day}\nTrabajadores: {workers}"
                        
                        global_point = self.continuity_canvas.mapToGlobal(QtCore.QPoint(event.x, event.y))
                        QtWidgets.QToolTip.showText(global_point, tooltip)
                        return  # Termina el bucle después de encontrar un punto cercano
            QtWidgets.QToolTip.hideText()  # Oculta el tooltip si el ratón no está cerca de ningún punto


    def populate_activities(self):
        # Obtener las actividades únicas de la agenda
        df = pd.read_csv("agenda.csv", encoding='ISO-8859-1')
        unique_activities = df['Activity'].unique()
        self.activityComboBox.addItems(unique_activities)

    def prepare_continuity_data(self):
        # Obtener el mes y año seleccionados
        month = self.selected_month
        year = self.selected_year

        # Leer datos de agenda.csv
        df = pd.read_csv("agenda.csv", encoding='ISO-8859-1')
        df['Date'] = pd.to_datetime(df['Date'])

        # Filtrar por mes y año seleccionados
        df = df[(df['Date'].dt.month == month) & (df['Date'].dt.year == year) & (df['Status'] == 'Approved')]

        # Crear un DataFrame para contar asignaciones por día y actividad
        count_df = df.groupby([df['Date'].dt.day, 'Activity']).size().unstack(fill_value=0)

        return count_df

    def get_workers_assigned_per_day(self, selected_activity):
        # Leer los datos y filtrar por la actividad y el estado 'Approved'
        df = pd.read_csv("agenda.csv", encoding='ISO-8859-1')
        df = df[(df['Activity'] == selected_activity) & (df['Status'] == 'Approved')]
        df['Date'] = pd.to_datetime(df['Date']).dt.day

        # Agrupar por día y obtener los nombres de los trabajadores
        workers_per_day = df.groupby('Date')['Name'].apply(list).to_dict()
        return workers_per_day

    
    def update_continuity_graph(self):
        selected_activity = self.activityComboBox.currentText()
        continuity_data = self.prepare_continuity_data()
        self.workers_per_day = self.get_workers_assigned_per_day(selected_activity)

        # Si la actividad seleccionada no está en los datos, retorna
        if selected_activity not in continuity_data.columns:
            print("Actividad seleccionada no disponible en los datos.")
            return

        # Preparar los datos para el gráfico
        activity_data = continuity_data[selected_activity]

        # Asegurarse de que haya una entrada para cada día del mes
        days_in_month = calendar.monthrange(self.selected_year, self.selected_month)[1]
        all_days = pd.Series([0] * days_in_month, index=range(1, days_in_month + 1))
        activity_data = activity_data.combine(all_days, max, fill_value=0)


        # Determinar el número máximo de asignaciones en un día para la actividad seleccionada
        max_assignments = int(activity_data.max())

        # Crear el gráfico
        self.continuity_figure.clear()
        ax = self.continuity_figure.add_subplot(111)


        # Crear una serie para cada número de asignaciones
        for num_assignments in range(1, max_assignments + 1):
            # Crear una serie de datos donde los días con al menos num_assignments asignaciones tienen un valor constante de num_assignments
            series_data = activity_data.apply(lambda x: num_assignments if x >= num_assignments else 0)
            # Dibujar la serie en el gráfico
            line, = ax.plot(series_data.index, series_data, marker='o', label=f"Al menos {num_assignments} Asignaciones", picker=5)

        ax.set_title(f"Continuidad de {selected_activity}")
        ax.set_xlabel("Día del Mes")
        ax.set_ylabel("Cantidad de Asignaciones")
        ax.set_yticks(range(1, max_assignments + 1))  # Establecer ticks del eje Y
        #ax.legend()  # Muestra la leyenda

        def onpick(event):
            day = event.artist.get_xdata()[event.ind][0]
            self.daySelected.emit(day)  # Emite la señal con el día seleccionado

        self.continuity_canvas.mpl_connect('pick_event', onpick)
        self.continuity_canvas.draw()


    def set_default_dates(self):
        # Establecer la fecha de inicio como el primer día del mes seleccionado
        start_date = QtCore.QDate(self.selected_year, self.selected_month, 1)
        self.startDateEdit.setDate(start_date)

        # Establecer la fecha de fin como el último día del mes seleccionado
        last_day = calendar.monthrange(self.selected_year, self.selected_month)[1]
        end_date = QtCore.QDate(self.selected_year, self.selected_month, last_day)
        self.endDateEdit.setDate(end_date)        

    def update_graph(self):
        # Obtener fechas seleccionadas
        start_date = self.startDateEdit.date().toString("yyyy-MM-dd")
        end_date = self.endDateEdit.date().toString("yyyy-MM-dd")        

       # Leer datos de agenda.csv y filtrar
        df = pd.read_csv("agenda.csv", encoding='ISO-8859-1')
        df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date) & (df['Status'] == 'Approved')]

        # Contar la frecuencia de cada actividad para cada trabajador
        activity_counts = df.groupby(['Id', 'Activity']).size().unstack(fill_value=0)
        activity_counts = activity_counts.assign(total=activity_counts.sum(axis=1)).sort_values(by='total', ascending=True).drop('total', axis=1)

        if activity_counts.empty:
            print("No hay datos para mostrar en el rango de fechas seleccionado.")
            self.figure.clear()
            self.canvas.draw()
            return  # Salir de la función si no hay datos

        # Verificar el contenido de activity_counts
        print(activity_counts)  # Agregar esto para depuración

        # Crear un mapeo de ID a 'Rank' y primera palabra de 'Name'
        id_to_label = {w['Id']: "{} {}".format(w['Rank'], w['Name'].split()[0]) for w in self.trabajadores}

        # Crear el gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Generar gráfico de barras apiladas
        bars = activity_counts.plot(kind='barh', stacked=True, ax=ax, legend=True)

        # Agregar anotaciones a las barras
        for bar in bars.patches:
            width = bar.get_width()
            if width > 0:
                x = bar.get_x() + width / 2
                y = bar.get_y() + bar.get_height() / 2
                ax.text(x, y, str(int(width)), ha='center', va='center')

        ax.set_ylabel('')
        ax.set_title('Frecuencia de Actividades por Trabajador')
        ax.set_xticks([])
        ax.set_yticklabels([id_to_label.get(idx) for idx in activity_counts.index])

        self.figure.subplots_adjust(left=0.2)
        self.canvas.draw()


#---------------------Incialización del Qtwidget----------------------------------
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    ventana = MiApp()
    ventana.showFullScreen()
    sys.exit(app.exec_())