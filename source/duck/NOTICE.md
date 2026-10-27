# Duck — Herkunft und Bearbeitung

Originalmodell: © 2006 Sony, „The COLLADA duck“, über Khronos glTF Sample Assets.
Lizenz: SCEA Shared Source License 1.0; vollständiger Text in LICENSE.txt.
Copyright-Hinweis aus der Lizenz: Copyright 2005 Sony Computer Entertainment Inc.

Quelle: https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/Duck
Direktdownload: https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Duck/glTF-Binary/Duck.glb
Lizenzquelle: https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/LICENSES/SCEA.txt
Originalbeschreibung: README_original.md, unverändert übernommen.
GLB SHA-256: 65bf938f54d6073e619e76e007820bbf980cdc3dc0daec0d94830ffc4ae54ab5

Bearbeitung für diesen Teststand: starre Geometrie aus der GLB-Szene extrahiert;
Y-oben nach Z-oben gedreht, zentriert und auf einen Einheitsbegrenzungsquader
normiert. Die Szenenabmessungen erhalten die Originalproportionen und setzen
hier die längste Seite auf 0.08 m. Textur/Material wurden entfernt; die Darstellung
ist einfarbig gelb. Zusätzlich wurde eine konvexe Kollisionshülle erzeugt.
Die Aufbereitung erfolgt reproduzierbar durch mesh_import.prepare_mesh().

Die angesetzte Masse von 0.06 kg, Reibung und starre Kollisionsdynamik sind eigene
Simulationsannahmen. Das ist kein gemessenes Modell einer realen Gummiente.
Die Anwendungslizenz ersetzt nicht die oben genannte Lizenz des Fremdmodells.
