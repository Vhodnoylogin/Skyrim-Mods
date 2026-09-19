#pragma once

// See skse64/PluginAPI.h in this folder for why these stand-ins exist.
//
// The contracts only ever take and return pointers to these, so a declaration is the
// whole of what is needed. Our own code holds the game's real RE:: types and casts at
// the boundary - that cast is the honest place where one mod's vocabulary ends and
// another's begins, and it is done in VrikLink.cpp and HiggsLink.cpp, nowhere else.

#include "skse64/NiTypes.h"

class TESForm;
class TESObjectREFR;
class BGSArtObject;
class Actor;
