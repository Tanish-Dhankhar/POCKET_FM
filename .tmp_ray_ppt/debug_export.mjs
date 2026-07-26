import { Presentation, PresentationFile } from "@oai/artifact-tool";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const s = p.slides.add();
s.background.fill = "linear(145deg, #050306 0%, #080407 56%, #1A050D 100%)";
const sh = s.shapes.add({
  geometry: "textbox",
  position: { left: 70, top: 70, width: 800, height: 100 },
  fill: "none",
  line: { style: "solid", fill: "none", width: 0 },
});
sh.text = "RAY";
sh.text.style = {
  typeface: "Silkscreen",
  fontSize: 60,
  bold: true,
  color: "#FFFFFF",
  alignment: "left",
  verticalAlignment: "top",
  autoFit: "shrinkText",
  wrap: "square",
  insets: { top: 0, right: 0, bottom: 0, left: 0 },
};
s.speakerNotes.textFrame.setText("Test notes\n\n[Sources]\n- https://github.com/google/fonts/tree/main/ofl/silkscreen");
s.speakerNotes.setVisible(true);
const pptx = await PresentationFile.exportPptx(p);
await pptx.save("output/debug.pptx");
