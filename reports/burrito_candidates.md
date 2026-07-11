# V-Sekai — Burrito-ready candidates

_Snapshot `2026-07-11T17:19:47Z` · 88 Elixir/C/C++/Python repos scored for how close they are to a shippable Elixir binary. Hexagonal read: domain core, an escript driving adapter, and a Burrito/hex.pm distribution adapter._

## Chosen finish-today tasks

Picked from the top burrito-ready candidates for being end-to-end usable avatar tools that are nearly done and bring closure.

### Primary: [V-Sekai-fire/cloth-fit](https://github.com/V-Sekai-fire/cloth-fit)

Route elixir, score 12, 1 open issue(s), pushed 2025-08-13. Elixir/Unifex CLI subdir wrapping a native core. Finish the CLI adapter and add a Burrito release to ship a cross-platform binary that dresses an avatar.

### Fallback: [V-Sekai/TOOL_cloth_dynamics](https://github.com/V-Sekai/TOOL_cloth_dynamics)

Route c, score 8, 1 open issue(s), pushed 2026-05-15. builds an executable. Independent backup with the same avatar-cloth payoff.

## Top 20 burrito-ready repos

| Rank | Repo                                                         | Route  | Lang   | CLI | ML  | Burrito | Pushed     | Score  | Why                                                                             |
| ---- | ------------------------------------------------------------ | ------ | ------ | --- | --- | ------- | ---------- | ------ | ------------------------------------------------------------------------------- |
| 1    | `V-Sekai-fire/cloth-fit`                                     | elixir | C++    | yes | no  | no      | 2025-08-13 | **12** | escript/Unifex CLI adapter present · native core already bound via Unifex       |
| 2    | `V-Sekai-fire/aria-gltf`                                     | elixir | Elixir | no  | yes | no      | 2026-03-14 | **12** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 3    | `V-Sekai-fire/aria-planner`                                  | elixir | Elixir | no  | yes | no      | 2026-03-15 | **12** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 4    | `V-Sekai-fire/aria-carbs`                                    | elixir | Elixir | no  | yes | no      | 2025-11-14 | **11** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 5    | `V-Sekai-fire/aria-math`                                     | elixir | Elixir | no  | yes | no      | 2026-03-14 | **11** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 6    | `V-Sekai-fire/ML_fire_juan_mosaic`                           | c      | C++    | yes | yes | no      | 2022-03-01 | **10** | C/C++ executable core, wrap via NIF/port · ML core, ship via pythonx and hex.pm |
| 7    | `V-Sekai-fire/aria-qcp`                                      | elixir | Elixir | no  | yes | no      | 2025-08-28 | **10** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 8    | `V-Sekai-fire/minicpm-vision`                                | elixir | Elixir | no  | yes | no      | 2025-10-08 | **10** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 9    | `V-Sekai-fire/aria-usd`                                      | elixir | Elixir | no  | yes | no      | 2025-11-13 | **10** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 10   | `V-Sekai-fire/aria-usd-tscn`                                 | elixir | Elixir | no  | yes | no      | 2025-11-13 | **10** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 11   | `V-Sekai-fire/aria-usd-unity`                                | elixir | Elixir | no  | yes | no      | 2025-11-13 | **10** | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 12   | `V-Sekai-fire/multiplayer-fabric-zone-console`               | elixir | Elixir | yes | no  | no      | 2026-04-29 | **10** | escript/Unifex CLI adapter present                                              |
| 13   | `v-sekai-multiplayer-fabric/fabric-platform-central`         | elixir | Elixir | no  | no  | yes     | 2026-06-25 | **10** | Elixir core, add an escript adapter · Burrito distribution configured           |
| 14   | `V-Sekai-fire/elixir-entity-database`                        | elixir | Elixir | no  | yes | no      | 2024-07-09 | **9**  | Elixir core, add an escript adapter · ML core, ship via pythonx and hex.pm      |
| 15   | `V-Sekai-fire/rf-detr`                                       | python | Python | yes | yes | no      | 2025-04-09 | **9**  | Python CLI entrypoint · ML core, ship via pythonx and hex.pm                    |
| 16   | `V-Sekai-fire/TOOL_agent_reinforcement_trainer`              | python | Python | yes | yes | no      | 2025-05-28 | **9**  | Python CLI entrypoint · ML core, ship via pythonx and hex.pm                    |
| 17   | `V-Sekai-fire/tosa-converter-for-tflite`                     | python | Python | yes | yes | no      | 2025-07-07 | **9**  | Python CLI entrypoint · ML core, ship via pythonx and hex.pm                    |
| 18   | `V-Sekai-fire/3dgs-ply2gltf`                                 | c      | C++    | yes | no  | no      | 2026-02-23 | **8**  | C/C++ executable core, wrap via NIF/port                                        |
| 19   | `V-Sekai/TOOL_cloth_dynamics`                                | c      | C++    | yes | no  | no      | 2026-05-15 | **8**  | C/C++ executable core, wrap via NIF/port                                        |
| 20   | `v-sekai-multiplayer-fabric/godot-sandbox-gdscript-compiler` | c      | C++    | yes | no  | no      | 2026-05-29 | **8**  | C/C++ executable core, wrap via NIF/port                                        |

### Score model

- driving adapter: elixir escript/Unifex CLI (+6); elixir library, add escript (+3); C/C++ executable (+4); Python CLI entrypoint (+3).
- native core bound via Unifex (+3); Burrito distribution configured (+3).
- ML core, ship via pythonx and hex.pm (+4).
- self-contained core, not web/server (+2); alive: pushed <6mo (+2) / <1y (+1); has description (+1); web/server driving adapter (−5).
