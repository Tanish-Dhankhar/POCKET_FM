import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const W = 1280;
const H = 720;
const OUT = path.resolve("output");
const ROOT = path.resolve("..");
const PPT_MD = path.join(ROOT, "ppt.md");

const C = {
  bg: "#050306",
  bg2: "#120309",
  panel: "#12080D",
  panel2: "#1A0910",
  accent: "#F03A66",
  accent2: "#FF6A8E",
  white: "#FFFFFF",
  muted: "#BDB4BA",
  dim: "#756A70",
  line: "#42101F",
  line2: "#6D1831",
  darkAccent: "#2A0712",
};

const F = {
  display: "Silkscreen",
  body: "JetBrains Mono",
};

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function addShape(slide, geometry, x, y, w, h, fill = "none", lineFill = "none", lineWidth = 0, name) {
  const config = {
    geometry,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  };
  if (name) config.name = name;
  return slide.shapes.add(config);
}

function addText(slide, text, x, y, w, h, opts = {}) {
  const shape = addShape(slide, "textbox", x, y, w, h, opts.fill ?? "none", opts.lineFill ?? "none", opts.lineWidth ?? 0, opts.name);
  shape.text = text;
  const textStyle = {
    typeface: opts.typeface ?? F.body,
    fontSize: opts.fontSize ?? 20,
    bold: opts.bold ?? false,
    color: opts.color ?? C.white,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: opts.wrap ?? "square",
    insets: opts.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  shape.text.style = textStyle;
  return shape;
}

function addLine(slide, x, y, w, h, color = C.line, width = 1) {
  const safeW = w === 0 ? 1 : w;
  const safeH = h === 0 ? 1 : h;
  return addShape(slide, "line", x, y, safeW, safeH, "none", color, width);
}

function addPixel(slide, x, y, size = 10, color = C.accent) {
  return addShape(slide, "rect", x, y, size, size, color, "none", 0);
}

function base(slide, index, section = "RAY // POCKET FM") {
  slide.background.fill = "linear(145deg, #050306 0%, #080407 56%, #1A050D 100%)";

  for (let y = 10; y < H; y += 24) {
    addShape(slide, "rect", 0, y, W, 1, y % 48 === 10 ? "#210811" : "#15070C", "none", 0);
  }

  addShape(slide, "rect", 0, 0, 10, H, C.accent, "none", 0);
  addShape(slide, "rect", 10, 0, 3, H, C.darkAccent, "none", 0);
  addText(slide, String(index).padStart(2, "0"), 42, 28, 52, 24, {
    typeface: F.display, fontSize: 14, color: C.accent, bold: true,
  });
  addText(slide, section, 912, 28, 310, 20, {
    fontSize: 12, color: C.dim, align: "right", bold: true,
  });
  addLine(slide, 42, 684, 1138, 0, C.line, 1);
  addPixel(slide, 1192, 680, 9, C.accent);
  addPixel(slide, 1206, 680, 9, C.white);
  addPixel(slide, 1220, 680, 9, C.line2);
}

function title(slide, text, sub) {
  addText(slide, text, 70, 72, 1110, 62, {
    typeface: F.display, fontSize: 38, bold: true, color: C.white,
  });
  addShape(slide, "rect", 70, 144, 82, 6, C.accent, "none", 0);
  if (sub) addText(slide, sub, 174, 136, 930, 32, { fontSize: 16, color: C.muted });
}

function label(slide, text, x, y, w, opts = {}) {
  return addText(slide, text, x, y, w, opts.h ?? 24, {
    typeface: F.display,
    fontSize: opts.fontSize ?? 15,
    bold: true,
    color: opts.color ?? C.accent,
    align: opts.align ?? "left",
  });
}

function notesFor(markdown, n) {
  const marker = new RegExp(`^## Slide ${n}\\b.*$`, "m");
  const match = markdown.match(marker);
  let extracted = "";
  if (match) {
    const start = match.index;
    const rest = markdown.slice(start + match[0].length);
    const next = rest.search(/^## Slide \d+\b/m);
    const chunk = next >= 0 ? rest.slice(0, next) : rest.split(/^## Presenter guardrails/m)[0];
    const timing = chunk.match(/\*\*Time:\s*([^*]+)\*\*/)?.[1]?.trim();
    const speakerStart = chunk.search(/^### Speaker script(?: and actions)?/m);
    if (speakerStart >= 0) {
      const speakerChunk = chunk.slice(speakerStart).replace(/^### Speaker script(?: and actions)?\s*/m, "");
      const stop = speakerChunk.search(/^### Visual direction/m);
      extracted = (stop >= 0 ? speakerChunk.slice(0, stop) : speakerChunk).trim();
    }
    if (timing) extracted = `Timing: ${timing}\n\n${extracted}`;
  }
  return `${extracted}\n\n[Sources]\n- Product content: local project files ppt.md, IDEA.MD, plan.md, AGENTIC_AUDIO_EDITOR.md, app/, and tests/.\n- Visual inspiration: user-provided ZERO TO ONE poster.\n- Silkscreen typeface: https://github.com/google/fonts/tree/main/ofl/silkscreen (SIL Open Font License).`;
}

function setNotes(slide, markdown, n) {
  slide.speakerNotes.textFrame.setText(notesFor(markdown, n));
  slide.speakerNotes.setVisible(true);
}

function addArrow(slide, x1, y1, x2, y2, color = C.accent) {
  const line = addLine(slide, x1, y1, x2 - x1, y2 - y1, color, 2);
  addShape(slide, "chevron", x2 - 12, y2 - 8, 16, 16, color, "none", 0);
  return line;
}

function featureRow(slide, n, name, detail, y) {
  addText(slide, String(n).padStart(2, "0"), 88, y, 72, 48, {
    typeface: F.display, fontSize: 28, bold: true, color: C.accent,
  });
  addLine(slide, 170, y + 21, 64, 0, C.line2, 2);
  addText(slide, name, 254, y - 2, 440, 32, {
    typeface: F.display, fontSize: 18, bold: true, color: C.white,
  });
  addText(slide, detail, 714, y, 452, 48, {
    fontSize: 15, color: C.muted, lineSpacing: 1.1,
  });
  addLine(slide, 254, y + 58, 912, 0, C.line, 1);
}

function flowNode(slide, n, name, detail, x, y, w = 240, h = 125) {
  addShape(slide, "rect", x, y, w, h, C.panel, C.line2, 1);
  addShape(slide, "rect", x, y, 7, h, n % 2 ? C.accent : C.white, "none", 0);
  addText(slide, String(n).padStart(2, "0"), x + 20, y + 14, 45, 24, {
    typeface: F.display, fontSize: 14, color: C.accent, bold: true,
  });
  addText(slide, name, x + 20, y + 45, w - 36, 28, {
    typeface: F.display, fontSize: 16, color: C.white, bold: true,
  });
  addText(slide, detail, x + 20, y + 78, w - 36, 36, {
    fontSize: 12, color: C.muted, lineSpacing: 1.05,
  });
}

async function main() {
  await fs.mkdir(OUT, { recursive: true });
  const markdown = await fs.readFile(PPT_MD, "utf8");
  const p = Presentation.create({ slideSize: { width: W, height: H } });

  // Slide 1
  {
    const s = p.slides.add();
    base(s, 1, "P6 // AI AGENTS");
    addText(s, "RAY", 72, 120, 650, 180, { typeface: F.display, fontSize: 124, bold: true, color: C.white });
    addText(s, "LET CREATORS CREATE.", 78, 312, 690, 54, { typeface: F.display, fontSize: 30, bold: true, color: C.accent });
    addText(s, "Pocket FM's end-to-end AI Creator Copilot", 80, 388, 650, 38, { fontSize: 21, color: C.white, bold: true });
    addText(s, "IDEA  >  SERIES  >  CINEMATIC AUDIO", 80, 447, 650, 28, { fontSize: 14, color: C.muted, bold: true });

    addShape(s, "rect", 820, 112, 290, 290, "none", C.line2, 3);
    addShape(s, "rect", 855, 147, 220, 220, C.darkAccent, C.accent, 2);
    const bars = [42, 86, 132, 76, 176, 116, 210, 138, 92, 156, 68];
    bars.forEach((h, i) => addShape(s, "rect", 884 + i * 16, 257 - h / 2, 9, h, i === 5 ? C.white : C.accent, "none", 0));
    addPixel(s, 806, 98, 18, C.white);
    addPixel(s, 1096, 388, 18, C.accent);
    addText(s, "THE CREATOR BRINGS THE SPARK.\nRAY BUILDS THE WORLD.", 816, 448, 330, 86, { typeface: F.display, fontSize: 17, bold: true, color: C.white, align: "center", lineSpacing: 1.2 });
    setNotes(s, markdown, 1);
  }

  // Slide 2
  {
    const s = p.slides.add();
    base(s, 2);
    title(s, "CREATORS DO NOT LACK IDEAS.");
    addText(s, "THEY LACK TIME + A PRODUCTION TEAM.", 72, 172, 1080, 54, { typeface: F.display, fontSize: 28, bold: true, color: C.accent });
    addShape(s, "rect", 74, 270, 190, 190, C.panel2, C.accent, 2);
    addText(s, "01", 98, 293, 60, 34, { typeface: F.display, fontSize: 22, bold: true, color: C.accent });
    addText(s, "BRILLIANT\nIDEA", 98, 343, 145, 78, { typeface: F.display, fontSize: 24, bold: true, color: C.white, lineSpacing: 1.1 });
    const jobs = ["STORY\nDEVELOPMENT", "EPISODE\nPLANNING", "SCRIPT\nWRITING", "CAST +\nVOICES", "SOUND\nDESIGN", "FINAL\nMIX"];
    jobs.forEach((job, i) => {
      const x = 338 + (i % 3) * 274;
      const y = 263 + Math.floor(i / 3) * 126;
      addText(s, String(i + 1).padStart(2, "0"), x, y, 38, 24, { typeface: F.display, fontSize: 12, color: C.accent, bold: true });
      addText(s, job, x + 46, y - 2, 180, 52, { typeface: F.display, fontSize: 16, bold: true, color: C.white, lineSpacing: 1.05 });
      addLine(s, x, y + 68, 220, 0, C.line2, 1);
    });
    addArrow(s, 274, 365, 322, 365, C.accent);
    addText(s, "CREATIVITY BECOMES COORDINATION.", 72, 552, 1100, 48, { typeface: F.display, fontSize: 27, bold: true, color: C.muted, align: "center" });
    setNotes(s, markdown, 2);
  }

  // Slide 3
  {
    const s = p.slides.add();
    base(s, 3);
    title(s, "ONE IDEA. ONE CONNECTED SERIES.", "A division of responsibility that protects creativity");
    addShape(s, "rect", 72, 214, 470, 320, C.panel, C.line2, 1);
    addShape(s, "rect", 738, 214, 470, 320, C.panel, C.line2, 1);
    label(s, "THE CREATOR BRINGS", 104, 246, 400, { fontSize: 18, color: C.white });
    addText(s, "IMAGINATION\nEMOTION\nTASTE\nFINAL SAY", 104, 306, 350, 170, { typeface: F.display, fontSize: 26, bold: true, color: C.accent, lineSpacing: 1.25 });
    label(s, "RAY HANDLES", 770, 246, 400, { fontSize: 18, color: C.white });
    addText(s, "PLANNING\nCONSISTENCY\nPRODUCTION\nEVALUATION\nCONTINUATION", 770, 306, 390, 190, { typeface: F.display, fontSize: 22, bold: true, color: C.accent2, lineSpacing: 1.2 });
    addShape(s, "ellipse", 578, 310, 124, 124, C.accent, "none", 0);
    addText(s, "RAY", 589, 350, 102, 40, { typeface: F.display, fontSize: 22, bold: true, color: C.white, align: "center" });
    addArrow(s, 542, 372, 574, 372, C.white);
    addArrow(s, 704, 372, 734, 372, C.white);
    addText(s, "RAY REMOVES REPETITIVE WORK — NOT CREATIVE CONTROL.", 70, 584, 1138, 36, { typeface: F.display, fontSize: 21, bold: true, color: C.white, align: "center" });
    setNotes(s, markdown, 3);
  }

  // Slide 4
  {
    const s = p.slides.add();
    base(s, 4);
    title(s, "FROM ROUGH IDEA TO GROWING SERIES", "Creator approval runs through every step");
    const nodes = [
      [1, "INPUT", "Write or speak the idea"],
      [2, "UNDERSTAND", "Extract premise + ask 4 questions"],
      [3, "BUILD", "World, characters, tone, plot"],
      [4, "PLAN", "Episode arcs, hooks, cliffhangers"],
      [5, "PRODUCE", "Script, cast, direct cinematic audio"],
      [6, "REVIEW", "Edit, evaluate, remix, approve"],
      [7, "CONTINUE", "Add a plot; create next episodes"],
    ];
    const xs = [70, 335, 600, 865];
    for (let i = 0; i < 4; i++) flowNode(s, ...nodes[i], xs[i], 208, 235, 120);
    for (let i = 0; i < 3; i++) addArrow(s, xs[i] + 235, 268, xs[i + 1] - 8, 268, C.line2);
    for (let i = 4; i < 7; i++) flowNode(s, ...nodes[i], 203 + (i - 4) * 310, 390, 270, 120);
    addArrow(s, 1100, 328, 1100, 372, C.accent);
    addArrow(s, 865, 450, 783, 450, C.line2);
    addArrow(s, 513, 450, 483, 450, C.line2);
    addLine(s, 204, 572, 886, 0, C.accent, 3);
    [204, 513, 823, 1090].forEach((x) => addPixel(s, x - 4, 568, 9, C.white));
    addText(s, "CREATOR APPROVAL", 502, 590, 290, 26, { typeface: F.display, fontSize: 14, bold: true, color: C.accent, align: "center" });
    setNotes(s, markdown, 4);
  }

  // Slide 5
  {
    const s = p.slides.add();
    base(s, 5, "DIFFERENT // 1 OF 2");
    title(s, "WHAT MAKES US DIFFERENT", "Story quality stays in the creator's hands");
    featureRow(s, 1, "FULL CREATIVE CONTROL", "Review • Edit • Regenerate • Approve at every stage", 202);
    featureRow(s, 2, "CLIFFHANGER-FIRST", "Every episode ends with a reason to play the next one", 300);
    featureRow(s, 3, "AI EVALUATOR JUDGE", "Checks hook, pacing, voices, escalation, clarity + ending", 398);
    featureRow(s, 4, "READY TO PUBLISH", "Final audio • Thumbnail • Title • Description • Metadata", 496);
    addShape(s, "rect", 62, 196, 8, 360, C.accent, "none", 0);
    addText(s, "CREATOR APPROVAL AT EVERY STAGE", 86, 608, 1080, 26, { typeface: F.display, fontSize: 14, bold: true, color: C.accent, align: "center" });
    setNotes(s, markdown, 5);
  }

  // Slide 6
  {
    const s = p.slides.add();
    base(s, 6, "DIFFERENT // 2 OF 2");
    title(s, "WHAT MAKES US DIFFERENT", "Ray builds a connected series — not isolated outputs");
    featureRow(s, 5, "STATE-OF-THE-ART AUDIO", "Emotion • Pauses • Overlap • Interruption • Cinematic mix", 202);
    featureRow(s, 6, "FLUID CONSISTENCY", "World, characters, relationships, voices + events stay connected", 300);
    featureRow(s, 7, "STORY EXTENSION + MEMORY", "Add a plot; Ray remembers, updates + makes the next episodes", 398);
    featureRow(s, 8, "AUTO-DUB + LOCALIZE", "New languages while preserving personality, emotion + continuity", 496);
    addShape(s, "rect", 62, 196, 8, 360, C.white, "none", 0);
    addText(s, "AUTO-DUBBING + PUBLISHING PACKAGE = PRODUCT EXPANSION", 86, 608, 1080, 26, { typeface: F.display, fontSize: 13, bold: true, color: C.dim, align: "center" });
    setNotes(s, markdown, 6);
  }

  // Slide 7
  {
    const s = p.slides.add();
    base(s, 7);
    title(s, "THREE MEMORIES PROTECT CONTINUITY", "Every new episode is generated with the full story state");
    const blocks = [
      ["SERIES BIBLE", "World rules\nMain plot\nTone + themes\nStory arcs"],
      ["CHARACTER BIBLE", "Role + personality\nBackstory + relationships\nVocal signature\nPersistent voice ID"],
      ["EPISODE LEDGER", "Previous events\nSummaries + scripts\nEmotional beats\nCliffhangers"],
    ];
    blocks.forEach(([head, body], i) => {
      const x = 72 + i * 388;
      addShape(s, "rect", x, 218, 340, 248, C.panel, i === 1 ? C.accent : C.line2, i === 1 ? 2 : 1);
      label(s, head, x + 24, 244, 292, { fontSize: 17, color: i === 1 ? C.accent : C.white });
      addText(s, body, x + 24, 302, 292, 132, { fontSize: 17, color: C.muted, lineSpacing: 1.35 });
      addLine(s, x + 24, 286, 292, 0, C.line2, 1);
      addArrow(s, x + 170, 466, 640, 526, i === 1 ? C.accent : C.line2);
    });
    addShape(s, "rect", 405, 526, 470, 74, C.accent, "none", 0);
    addText(s, "NEW PLOT  >  UPDATE STATE  >  CONNECTED EPISODES", 424, 548, 432, 30, { typeface: F.display, fontSize: 15, bold: true, color: C.white, align: "center" });
    addText(s, "REMEMBERS WHAT CHANGED — AND WHAT MUST NEVER CHANGE", 72, 626, 1136, 24, { typeface: F.display, fontSize: 13, bold: true, color: C.dim, align: "center" });
    setNotes(s, markdown, 7);
  }

  // Slide 8
  {
    const s = p.slides.add();
    base(s, 8);
    title(s, "RAY PRODUCES SCENES — NOT STITCHED SPEECH", "Typical: Text  >  TTS  >  File");
    const steps = [
      [1, "DIRECT", "Script + emotion + voice bible"],
      [2, "GENERATE ONCE", "Immutable TTS take per line"],
      [3, "PERFORM", "Pause • pace • overlap • interrupt"],
      [4, "BUILD THE WORLD", "Ambience • music • SFX • stereo"],
      [5, "PROTECT DIALOGUE", "Speech-aware ducking • safe master"],
      [6, "REMIX FAST", "Same voices • new direction • no TTS"],
    ];
    steps.forEach((st, i) => {
      const x = 74 + (i % 3) * 388;
      const y = 206 + Math.floor(i / 3) * 188;
      flowNode(s, ...st, x, y, 340, 132);
      if (i % 3 < 2) addArrow(s, x + 340, y + 66, x + 376, y + 66, C.accent);
    });
    addArrow(s, 1102, 338, 1102, 382, C.accent);
    addText(s, "VOICE TAKES STAY IMMUTABLE. DIRECTION STAYS EDITABLE.", 73, 592, 1138, 34, { typeface: F.display, fontSize: 19, bold: true, color: C.accent, align: "center" });
    setNotes(s, markdown, 8);
  }

  // Slide 9
  {
    const s = p.slides.add();
    base(s, 9);
    title(s, "STATEFUL AGENT. DETERMINISTIC PRODUCTION.");
    const layers = [
      ["CREATOR STUDIO", "React • Ideaboard • Episode editor • Playback • Audio Director"],
      ["API + ORCHESTRATION", "FastAPI • Background jobs • LangGraph • Human approval gates"],
      ["AI SPECIALISTS", "OpenAI structured reasoning • Gemini transcription + multi-voice TTS"],
      ["DETERMINISTIC AUDIO ENGINE", "Timeline • overlap • ducking • ambience • mix • master"],
    ];
    layers.forEach(([head, body], i) => {
      const y = 190 + i * 105;
      addShape(s, "rect", 72, y, 820, 78, i % 2 ? C.panel2 : C.panel, C.line2, 1);
      addText(s, String(i + 1).padStart(2, "0"), 92, y + 22, 52, 25, { typeface: F.display, fontSize: 14, bold: true, color: C.accent });
      addText(s, head, 160, y + 16, 310, 28, { typeface: F.display, fontSize: 17, bold: true, color: C.white });
      addText(s, body, 480, y + 16, 380, 46, { fontSize: 13, color: C.muted });
      if (i < 3) addArrow(s, 462, y + 78, 462, y + 101, C.accent);
    });
    addShape(s, "rect", 946, 190, 262, 393, C.darkAccent, C.accent, 2);
    label(s, "DURABLE SERIES MEMORY", 972, 220, 210, { fontSize: 15, color: C.white, h: 52 });
    addLine(s, 972, 280, 210, 0, C.accent, 2);
    addText(s, "ATOMIC JSON\n\nCHARACTER FILES\n\nEPISODE FOLDERS\n\nIMMUTABLE WAVS\n\nTTS CACHE", 972, 312, 210, 224, { typeface: F.display, fontSize: 14, bold: true, color: C.accent2, lineSpacing: 1.15 });
    [228, 333, 438, 543].forEach((y) => addLine(s, 892, y, 54, 0, C.accent, 2));
    addText(s, "RESTARTABLE • INSPECTABLE • SELECTIVELY REGENERATED", 72, 622, 1136, 24, { typeface: F.display, fontSize: 13, bold: true, color: C.dim, align: "center" });
    setNotes(s, markdown, 9);
  }

  // Slide 10
  {
    const s = p.slides.add();
    base(s, 10, "90 SECOND DEMO");
    addText(s, "LIVE", 72, 124, 800, 110, { typeface: F.display, fontSize: 82, bold: true, color: C.white });
    addText(s, "DEMO", 72, 222, 800, 110, { typeface: F.display, fontSize: 82, bold: true, color: C.accent });
    const stages = [["01", "SPOKEN IDEA"], ["02", "CONNECTED WORLD"], ["03", "CINEMATIC EPISODE"]];
    stages.forEach(([n, text], i) => {
      const x = 78 + i * 370;
      addText(s, n, x, 432, 52, 24, { typeface: F.display, fontSize: 13, bold: true, color: C.accent });
      addText(s, text, x, 468, 300, 50, { typeface: F.display, fontSize: 20, bold: true, color: C.white });
      if (i < 2) addArrow(s, x + 280, 486, x + 350, 486, C.accent);
    });
    const bars = [22, 48, 84, 38, 110, 58, 126, 72, 44, 92, 30, 66, 20];
    bars.forEach((h, i) => addShape(s, "rect", 890 + i * 20, 236 - h / 2, 10, h, i % 4 === 0 ? C.white : C.accent, "none", 0));
    addText(s, "IDEABOARD  >  PLAY 15 SEC  >  EVALUATOR  >  REMIX", 72, 606, 1136, 26, { fontSize: 14, bold: true, color: C.muted, align: "center" });
    setNotes(s, markdown, 10);
  }

  // Slide 11
  {
    const s = p.slides.add();
    base(s, 11);
    title(s, "MORE GREAT STORIES REACH PLAY", "Ray solves a creator problem and a platform problem together");
    addShape(s, "rect", 72, 218, 360, 272, C.panel, C.line2, 1);
    label(s, "FOR CREATORS", 98, 244, 300, { fontSize: 18, color: C.white });
    addText(s, "MORE ORIGINALITY\nLESS REPETITIVE WORK\nCOMPLETE CREATIVE CONTROL", 98, 308, 296, 144, { typeface: F.display, fontSize: 17, bold: true, color: C.accent, lineSpacing: 1.35 });

    addShape(s, "ellipse", 506, 266, 220, 220, C.accent, "none", 0);
    addShape(s, "rightTriangle", 588, 322, 78, 96, C.white, "none", 0);
    addText(s, "PLAY", 546, 510, 140, 30, { typeface: F.display, fontSize: 17, bold: true, color: C.white, align: "center" });

    addShape(s, "rect", 800, 218, 408, 272, C.panel, C.line2, 1);
    label(s, "FOR POCKET FM", 826, 244, 340, { fontSize: 18, color: C.white });
    addText(s, "FASTER CONCEPT TO PILOT\nMORE IDEAS TESTED\nCONNECTED LONG-RUNNING IP\nGLOBAL REACH", 826, 302, 344, 160, { typeface: F.display, fontSize: 16, bold: true, color: C.accent2, lineSpacing: 1.28 });
    addText(s, "30", 126, 556, 110, 58, { typeface: F.display, fontSize: 38, bold: true, color: C.white });
    addText(s, "VOICES", 226, 572, 132, 24, { typeface: F.display, fontSize: 15, bold: true, color: C.accent });
    addText(s, "131", 468, 556, 140, 58, { typeface: F.display, fontSize: 38, bold: true, color: C.white });
    addText(s, "AUTOMATED TESTS", 588, 572, 220, 24, { typeface: F.display, fontSize: 15, bold: true, color: C.accent });
    addText(s, "DURABLE CONTINUITY + CINEMATIC AUDIO DIRECTOR", 844, 562, 340, 44, { typeface: F.display, fontSize: 13, bold: true, color: C.muted, align: "center" });
    setNotes(s, markdown, 11);
  }

  // Slide 12
  {
    const s = p.slides.add();
    base(s, 12, "RAY // THE CLOSE");
    addShape(s, "rect", 646, 0, 634, H, "linear(90deg, #120309 0%, #2A0712 100%)", "none", 0);
    addText(s, "LET CREATORS", 74, 132, 1100, 82, { typeface: F.display, fontSize: 52, bold: true, color: C.white });
    addText(s, "CREATE.", 74, 214, 1100, 82, { typeface: F.display, fontSize: 52, bold: true, color: C.white });
    addText(s, "LET RAY", 74, 324, 1100, 82, { typeface: F.display, fontSize: 52, bold: true, color: C.accent });
    addText(s, "DO THE REST.", 74, 406, 1100, 82, { typeface: F.display, fontSize: 52, bold: true, color: C.accent });
    addText(s, "MORE HIGH-QUALITY, BINGE-WORTHY SERIES — FASTER, WITHOUT COMPROMISING CREATIVE CONTROL.", 76, 548, 1030, 60, { fontSize: 17, bold: true, color: C.white, lineSpacing: 1.15 });
    const bars = [32, 72, 46, 110, 62, 154, 88, 126, 44, 96];
    bars.forEach((h, i) => addShape(s, "rect", 1035 + i * 17, 240 - h / 2, 9, h, i === 5 ? C.white : C.accent, "none", 0));
    setNotes(s, markdown, 12);
  }

  if (process.env.SKIP_RENDER !== "1") {
    for (const [i, slide] of p.slides.items.entries()) {
      const stem = `slide-${String(i + 1).padStart(2, "0")}`;
      await writeBlob(path.join(OUT, `${stem}.png`), await p.export({ slide, format: "png", scale: 1 }));
      const layout = await slide.export({ format: "layout" });
      await fs.writeFile(path.join(OUT, `${stem}.layout.json`), await layout.text());
    }
    await writeBlob(path.join(OUT, "ray-montage.webp"), await p.export({ format: "webp", montage: true, scale: 1 }));
  }
  const keepThrough = Number(process.env.KEEP_THROUGH || 0);
  if (keepThrough > 0) {
    for (const slide of [...p.slides.items].reverse()) {
      if (slide.index >= keepThrough) p.slides.remove(slide);
    }
  }
  const pptx = await PresentationFile.exportPptx(p);
  await pptx.save(path.join(OUT, "Ray_Pocket_FM_Pitch.pptx"));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
