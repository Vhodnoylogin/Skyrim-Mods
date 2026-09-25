#include "game/Body.h"

#include <array>

namespace BodyPouches::Game
{
	namespace
	{
		// VRIK's own table of which bone each slot hangs on, as its DLL has it
		// (vrik-holster-api.md, "Положение кобуры").
		constexpr std::array<const char*, 14> kBones{
			"NPC COM [COM ]",         // 1  Left Hip
			"NPC Pelvis [Pelv]",      // 2  Right Hip
			"NPC L Thigh [LThg]",     // 3  Left Thigh
			"NPC R Thigh [RThg]",     // 4  Right Thigh
			"NPC L Calf [LClf]",      // 5  Left Calf
			"NPC R Calf [RClf]",      // 6  Right Calf
			"NPC L UpperArm [LUar]",  // 7  Left Upper Arm
			"NPC R UpperArm [RUar]",  // 8  Right Upper Arm
			"NPC L Forearm [LLar]",   // 9  Left Forearm
			"NPC R Forearm [RLar]",   // 10 Right Forearm
			"NPC L Clavicle [LClv]",  // 11 Left Shoulder
			"NPC R Clavicle [RClv]",  // 12 Right Shoulder
			"NPC Spine1 [Spn1]",      // 13 Stomach
			"NPC Spine2 [Spn2]",      // 14 Chest
		};
	}

	const char* Body::BoneOf(int a_slot) noexcept
	{
		return a_slot >= 1 && a_slot <= static_cast<int>(kBones.size()) ? kBones[a_slot - 1] : nullptr;
	}

	std::optional<RE::NiTransform> Body::Bone(int a_slot)
	{
		const char* name = BoneOf(a_slot);
		return name != nullptr ? BoneNamed(name) : std::nullopt;
	}

	std::optional<RE::NiTransform> Body::BoneNamed(const char* a_name)
	{
		auto* player = RE::PlayerCharacter::GetSingleton();
		if (player == nullptr || a_name == nullptr) {
			return std::nullopt;
		}
		// The third-person skeleton: that is the body VRIK draws, and its slots hang on it.
		auto* root = player->Get3D(false);
		if (root == nullptr) {
			return std::nullopt;
		}
		auto* bone = root->GetObjectByName(a_name);
		if (bone == nullptr) {
			return std::nullopt;
		}
		return bone->world;
	}

	RE::NiPoint3 Body::ToSlot(const RE::NiTransform& a_bone, const RE::NiPoint3& a_world)
	{
		const float scale = a_bone.scale != 0.0f ? a_bone.scale : 1.0f;
		return (a_bone.rotate.Transpose() * (a_world - a_bone.translate)) / scale;
	}

	RE::NiPoint3 Body::ToWorld(const RE::NiTransform& a_bone, const RE::NiPoint3& a_slot)
	{
		return a_bone.translate + a_bone.rotate * (a_slot * a_bone.scale);
	}

	RE::NiPoint3 Body::Axis(const RE::NiTransform& a_bone, int a_axis)
	{
		const auto& m = a_bone.rotate.entry;
		return { m[0][a_axis], m[1][a_axis], m[2][a_axis] };
	}
}
