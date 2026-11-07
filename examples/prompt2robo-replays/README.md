# Prompt2Robo auf dem LARA 5

Die Videos zeigen Programme aus dem Trainingssplit auf dem LARA 5 aus der Live-Simulation. Alle sechs gezeigten Programme erfüllten die Zielbedingungen. Die Videos wurden in 960 × 720 Pixeln gerendert und laufen mit zweifacher Wiedergabegeschwindigkeit. [Prüfbericht und Prüfsummen](manifest.json)

| Video | Aufgabe |
|---|---|
| [Rot auf Blau](bse-drop_onto_cube-000.mp4) | Rot aus 5 cm Höhe auf Blau fallen lassen |
| [Stapel mit Drehung](abs-stack_cube_on_cube-117.mp4) | Weiß auf Schwarz setzen, dann den Greifer auf 37,25° drehen |
| [Fallversuch](bse-drop_height_position-000.mp4) | Rot aus 10 cm Höhe am Ziel fallen lassen |
| [Viererlinie](abs-arrange_2d_line-000.mp4) | Vier Würfel auf einer Linie anordnen |
| [Pyramide](abs-pyramid_2_layer-000.mp4) | Pyramide mit zwei Ebenen bauen |
| [Greiferdrehung](sexp-v2-rotation_explicit_turn-001.mp4) | Den Greifer auf die Zielhöhe bewegen und auf 45° drehen |

Beim zusätzlichen Lauf `abs-v4-referencing_top_beside_tower-001` stößt die Greiferhand beim Absetzen an den Turm. Das Ergebnis ist im Prüfbericht als Fehler erfasst. `edge-already_solved-000` bestand die Textprüfung. [Einrichtung und Befehle](../../docs/prompt2robo.md)

Im separaten Split `eval_v4` bestanden 7 von 12 Referenzprogrammen. Der Bericht hält erreichte Ziele, Bewegungsfehler und Abweichungen fest. [Eval-Bericht](eval_v4-manifest.json)
