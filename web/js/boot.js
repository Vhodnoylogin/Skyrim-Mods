"use strict";

// ---- запуск ---------------------------------------------------------------------------------
const s = DATA.summary;
document.getElementById("title").textContent = "morphbench — " + (DATA.names.nif || T.noMesh);
document.getElementById("subtitle").textContent = s
  ? T.summaryMorphs + (DATA.names.tri ? DATA.names.tri + " (" + s.triKind + ")" : T.noTri) +
    T.summaryShapes + s.shapes + T.summaryVerts + s.vertices + T.summaryBones + s.bones + T.summarySliders + s.morphs +
    (DATA.names.skeleton ? T.summarySkeleton + DATA.names.skeleton + T.summaryCapsules + s.colliders : "")
  : (DATA.server ? T.chooseMesh : "");
try {
  window.mb = new App(DATA);
} catch (e) {
  const box = document.getElementById("nogl");
  box.style.display = "flex";
  box.textContent = T.cannotStart + (e.message || e);
  console.error(e);
}
