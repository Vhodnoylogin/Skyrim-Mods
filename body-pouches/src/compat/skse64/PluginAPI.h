#pragma once

// A stand-in for the SKSE64 header the two published contracts include.
//
// WHY THIS FILE EXISTS. `vrikinterface001.h` and `higgsinterface001.h` are taken from
// their authors verbatim and must stay that way - they are the contract, and a contract
// edited by one side is not one. They were written against the old SKSE64 SDK, while
// this plugin is built on CommonLibSSE-NG, so the names they expect have to come from
// somewhere. They come from here.
//
// Nothing below is a reimplementation of anything. These are names and layouts, just
// enough for the compiler to lay out a v-table of pointers correctly; every call still
// goes to the other mod's own code. The one rule for this file: only add what a
// contract actually asks for, and never anything with behaviour in it.

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

using UInt8 = std::uint8_t;
using UInt16 = std::uint16_t;
using UInt32 = std::uint32_t;
using UInt64 = std::uint64_t;
using SInt32 = std::int32_t;

// SKSE hands every plugin one of these at load; both contracts only ever pass it
// through to the handshake, which this plugin performs itself (see VrikLink.cpp), so
// the spelling is all that is needed.
using PluginHandle = UInt32;

// Only ever used as a pointer in the contracts' handshake declarations. The handshake
// itself is ours and goes through CommonLibSSE, so this type is never dereferenced.
struct SKSEMessagingInterface;
