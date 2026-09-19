#pragma once

// See skse64/PluginAPI.h in this folder for why these stand-ins exist.
//
// The two types below are returned BY VALUE by functions in the contracts, so their
// size and layout have to match the game's - a forward declaration would not compile
// and a wrong layout would corrupt the stack. They are the game's, copied field for
// field, and they carry no behaviour.

#include "skse64/PluginAPI.h"

// Skyrim's NiPoint3: three floats, nothing else.
struct NiPoint3
{
	float x{};
	float y{};
	float z{};
};

// Skyrim's NiTransform: rotation, translation, scale - 13 floats in that order.
// Only HIGGS's grab-transform pair uses it, and this plugin calls neither; the type is
// here so that the contract compiles as published.
struct NiMatrix33
{
	float entry[3][3]{};
};

struct NiTransform
{
	NiMatrix33 rotate;
	NiPoint3   translate;
	float      scale{ 1.0f };
};

class NiObject;
class NiAVObject;
class NiNode;
