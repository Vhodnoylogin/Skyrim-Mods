#pragma once

#include <RE/Skyrim.h>

#include <optional>

namespace BodyPouches::Game
{
	// Where a VRIK slot is on the player's body, worked out the way VRIK works it out.
	//
	// Every slot hangs on a bone of the third-person skeleton, and its posXN, posYN and
	// posZN in vrikslots.ini are an offset in that bone's own axes, times the bone's world
	// scale (claude-skyrim-vr/knowledge/vrik-holster-api.md, "Положение кобуры"):
	//
	//     the slot in the world = t + R * (s * pos)        pos = R^T * (p - t) / s
	//
	// Nothing here moves a slot - VRIK reads the positions only when the game starts. It
	// only says where a slot is, and which numbers would put it somewhere else.
	class Body
	{
	public:
		// The bone VRIK hangs this slot on, for slots 1..14; nullptr for anything else.
		[[nodiscard]] static const char* BoneOf(int a_slot) noexcept;

		// That bone's world transform right now, if the player's body is there at all.
		[[nodiscard]] static std::optional<RE::NiTransform> Bone(int a_slot);

		// Any other bone of the same body, by name.
		[[nodiscard]] static std::optional<RE::NiTransform> BoneNamed(const char* a_name);

		// A point in the world, as the posX, posY and posZ that would put the slot there.
		[[nodiscard]] static RE::NiPoint3 ToSlot(const RE::NiTransform& a_bone, const RE::NiPoint3& a_world);

		// And back: a slot's posX, posY and posZ, as a point in the world.
		[[nodiscard]] static RE::NiPoint3 ToWorld(const RE::NiTransform& a_bone, const RE::NiPoint3& a_slot);

		// One of the bone's own axes - 0, 1 or 2 for X, Y and Z - as a direction in the world.
		[[nodiscard]] static RE::NiPoint3 Axis(const RE::NiTransform& a_bone, int a_axis);
	};
}
