"use strict";

// ---- данные ядра, как они вложены в страницу ----------------------------------------------
class Shape {
  constructor(raw) {
    this.name = raw.name;
    this.base = Codec.f32(raw.vertices);          // исходные вершины, не трогаются
    this.pos = new Float32Array(this.base);        // вершины с применёнными ползунками
    this.nrm = new Float32Array(this.base.length); // нормали вершин по деформированным позициям
    this.count = raw.vertexCount;
    this.tris = Codec.index(raw.triangles, raw.indexType);
    this.triCount = this.tris.length / 3;
    this.boneKey = Codec.i16(raw.boneKey);
    this.boneNames = raw.boneNames;
    this.heldBones = raw.heldBones;      // кости с вершинами: по ним видимость капсул
  }
}

class Deltas {
  // Смещения одного морфа на одной части: номера вершин и int16-векторы с общим множителем.
  constructor(raw) {
    this.indices = Codec.index(raw.indices, raw.indexType);
    this.q = Codec.i16(raw.offsets);
    this.scale = raw.scale;
    this.count = raw.count;
  }
  applyTo(pos, amount) {
    const k = amount * this.scale, idx = this.indices, q = this.q;
    for (let i = 0, n = idx.length; i < n; i++) {
      const v = idx[i] * 3, j = i * 3;
      pos[v] += k * q[j]; pos[v + 1] += k * q[j + 1]; pos[v + 2] += k * q[j + 2];
    }
  }
  lengthsInto(out) {
    const idx = this.indices, q = this.q, k = this.scale;
    for (let i = 0, n = idx.length; i < n; i++) {
      const j = i * 3;
      out[idx[i]] = k * Math.sqrt(q[j] * q[j] + q[j + 1] * q[j + 1] + q[j + 2] * q[j + 2]);
    }
  }
}

class Strain {
  constructor(raw) {
    this.indices = Codec.index(raw.indices, raw.indexType);
    this.values = Codec.u8(raw.values);
    this.max = raw.max;
  }
  valuesInto(out) {
    const idx = this.indices, v = this.values, k = this.max / 255.0;
    for (let i = 0, n = idx.length; i < n; i++) out[idx[i]] = v[i] * k;
  }
}

// Кусок капсул - капсулы одной кости либо бампер, - как его отдают collider_meshes() и
// bumper_mesh() фасада: уже в мировых координатах, без морфов, поэтому ползунки его
// не трогают и нормали считаются один раз. Поля те же, что у Shape, - рисующему всё равно;
// bone - кость, на которой висит кусок (у бампера null).
class ColliderMesh {
  constructor(name, raw, bone) {
    this.name = name;
    this.bone = bone === undefined ? null : bone;
    this.pos = Codec.f32(raw.vertices);
    this.count = raw.vertexCount;
    this.tris = Codec.index(raw.triangles, raw.indexType);
    this.triCount = this.tris.length / 3;
    this.nrm = vertexNormals(this.pos, this.tris, new Float32Array(this.pos.length));
  }
}
