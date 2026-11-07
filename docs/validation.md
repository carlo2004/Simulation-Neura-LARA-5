# Prüfen

Die Softwaretests laufen mit der Projektumgebung. Sie prüfen unter anderem LARA-Geometrie, Kontakte, manuelle Steuerung, Datensatzformat, begrenzte Programmausführung und die Auswahl der CUDA-Runtime.

~~~bash
python bootstrap.py --test
node web/build.mjs
~~~

Für eine physische Kontrolle ohne Modell kannst du einen Referenzfall wiedergeben. Verwende einen neuen Ausgabeordner pro Lauf.

~~~bash
.venv/bin/python -m stacklab prompt2robo replay \
  --id bse-drop_onto_cube-000 --video --output runs/check-rot-auf-blau
~~~

Der Bericht enthält Start- und Endzustand und die Gründe der Zielwertung. Für einen End-to-End-Test in der Workbench wähle **Rot auf Blau**, lasse den Datensatzauftrag stehen und starte die gewünschte Modellseite. Die unabhängige Zielprüfung bewertet den ausgeführten Code. [Replay und Export](prompt2robo.md) · [Modellvergleich](workbench.md)

Die Skripte `tools/validate.py`, `tools/validate_objects.py` und `tools/validate_controls.py` prüfen die lokale Physik und Bedienung ausführlicher. Unter Linux kann MuJoCo bei Bedarf über `MUJOCO_GL=osmesa` mit installiertem `libosmesa6` rendern. Das Colab-Notebook richtet diesen Pfad ein.
