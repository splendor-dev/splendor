```text
$ splendor source freshness
Source freshness preview
Summary: total=52 unchanged=25 changed=27 missing=0 unsupported=0 historical=0
- .agent-plan.md: changed title=.agent plan logical_id=source:.agent-plan.md source_id=src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696
  Manifest: /private/tmp/hocrgen-splendor-refresh-test/state/manifests/sources/src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696.json
  Manifest checksum: 44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696
  Current checksum: d0ffed432c58784f5b985ef8cb718ad6f2cbc2acc2a3be1f356d438f1ce0a512
  Message: canonical workspace source differs from latest manifest checksum
  Next: splendor source refresh .agent-plan.md
  Next: splendor source refresh .agent-plan.md --apply
  Next: splendor ingest --pending --apply
...
Summary included 27 changed sources, including .agent-plan.md, README.md, docs/HeOCR_hocrgen_long_term_roadmap.md, docs/pre_alpha_freeze_plan.md, docs/release_governance.md, docs/source_adapter_contribution_guide.md, docs/synthetic_asset_contribution_guide.md, docs/2026_05_02_heocrsyn_spinout/*, and key src/hocrgen files.

$ splendor ingest --changed
Stale ingest
Initial freshness: total=52 unchanged=25 changed=27 missing=0 unsupported=0 historical=0
- .agent-plan.md: refreshed src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696 -> src-d0ffed432c58784f5b985ef8cb718ad6f2cbc2acc2a3be1f356d438f1ce0a512
- src/hocrgen/package/alpha.py: refreshed src-83f63fa5b1a448ac62b77c5b43dd15c78d21a2fa020d203622f16e17f34c0e10 -> src-fea43f00e07588f21942f784ac2c3796535120d38a6294e79c9361dba2c3693b
- src/hocrgen/fetchers/base.py: refreshed src-4a98a45e36a5b81caf8469cf906a273d0b28e0ce04dbed48b3a503bd3902e755 -> src-b451ae40adc4247063c6cb4e26b755b7eff4a99cf9a56273d0e3585b4d101cc5
- src/hocrgen/benchmark.py: refreshed src-0561b14d6a9f09cc3fcd3824f1a0b8885e65e52b607e8a5cadbdd6fa7f33a17d -> src-f5957a324296c6a762c108f9f091632006ac2af4d103a8f4e36582bdc6f1fec6
- src/hocrgen/fetchers/biblia.py: refreshed src-d4c2c30bdbf4d27cb63489e6c3f2045f1526dc1fcfeea0c516c8aff2eb5503f2 -> src-89c41e3b97571ae0d0a3b9802c8e7f39fa3e08e9199077e81c5f8925b924b2dc
- src/hocrgen/cli.py: refreshed src-8ec8d8c7f652e9a55cd9d0ea8fb96420b1e8071c2f87680cdf02ccddfea6a246 -> src-320e5722f67ded6445ac1f19234691ed35ee5eda5fe22579044385aa37c3f84e
- docs/HeOCR_hocrgen_long_term_roadmap.md: refreshed src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32 -> src-9f2cb4da3079d49d0107ebe680916d807f23abd7332e64116f07881c3ad9fdb2
- docs/hocrgen_design_and_spec.md: refreshed src-c9bf621a4a08694fff9fbbc2315b560dd7b5888034e37467b9d1c5a49f46393f -> src-a4309b3114a19627aaaeb738b094e954647f5afe1a2320a39a6afd7bb5de8a62
- docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_chatgpt.md: refreshed src-e185635b13b3c908dfbaa711ed6afa334f354ead32d827fb68cab2e561c19a25 -> src-21c2f369e5c9fbdbf231e21b54ed3187f87144b8e592ce17a01eb79c7c909448
- docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_gemini_1.md: refreshed src-7ae422c3690537954e41bddc048cc5c17629be8d76b1621f1f6fbcbeabb6bd9d -> src-83c2f616c8992d1a39ec17faa1242723cd4eced342940f0744591d43b3bb967d
- docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_gemini_2.md: refreshed src-1973d8ec01bb4e636ad2308ef9512037f062bd8c132da3017859e12fa257b379 -> src-acad19cdded112f57a0ce46b5a40222784b93cb877fcae8ae6e1a594b1dc9feb
- src/hocrgen/config/licenses.yaml: refreshed src-971f32069b2f2c2611a2e217ff9c4df10168a170f44f43af473663bf0e3a9b72 -> src-9bfba566e0f9a804dfb6a0ab5797fe983fb2a7a39e1fb96375f8d546ce27fdaa
- src/hocrgen/config/loader.py: refreshed src-f017f2efcbbfa07f397c9930ea3793f5cb6533a420334227ebef033c388de1fb -> src-544d37ee7f45565b0a4a62295b9ecebfd4ad3e74df75d54c5222cfe27f62027c
- src/hocrgen/config/models.py: refreshed src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61 -> src-36278eff64e8cc69e95f31e1dea5388a86b2ab4856aa0d003805690e929a3564
- src/hocrgen/manifests/models.py: refreshed src-be89457a63cbe7a028944287494a0cecc0c6c8f5da3d49f0050d48b6b6f8fb50 -> src-0bfd85d7c981ae45f388c1438259278f2aaae8e958de18f4fc3efa7a28345456
- src/hocrgen/fetchers/nli.py: refreshed src-d76cc18a7d533e5085d4cc98c81687ebe3492ca8cf1395e4bfd781ca4b3b92f0 -> src-8cfe922a24198d7456f1c0702c120bd5ecb05796dc5556c0ea00c3517ae5f1da
- src/hocrgen/fetchers/pinkas.py: refreshed src-a586b8dfff3260278e7afa8f70497c6c3d99644a2632af8dd2548cf23003d3c2 -> src-8217726aca6aa14678428419d5273bc0759fcb52f04750801d65bd956932ed34
- src/hocrgen/pipeline.py: refreshed src-f947470a59c2a7839ec2b42d05af523c06e621e58b6e3e3d9f07c2fa3f790f35 -> src-ebfb17ec27fccc7e3973c3ebbad5191a64178e7178bf7ed46ae2b379ec6f5e9c
- docs/pre_alpha_freeze_plan.md: refreshed src-0d280c17bdc9daee7b0acc4c01972a171ee24de5178b149874b0aec524ef0376 -> src-c83843183f2e8a10c4da1936e9087884f7989b06822a0ba4c94cdd0742c3d836
- src/hocrgen/review/queue.py: refreshed src-d35450808b548f78d689a33e3f28a788ebd93da5ee5e2296a60082db4906d6d2 -> src-532cb24bf59e19afc51f055ad02569d6f3d32b5038c0d3ebb6de3f65a0989c99
- README.md: refreshed src-6cd7017ff09d2b3301e01611897211da36f013848bf2da840f5400f47caf7d9b -> src-2b6c37ab98effe110e15c5a99f5b39643d578c0650285919d56f0eebf4a7cd9c
- docs/release_governance.md: refreshed src-45b84be09c1d6cc3524d1b4047af8e013fd0a855abd750df7d6759466c721855 -> src-0c27f7acefdf9bf5d8869396ffe458d04a688dc09c9f53832994cafa20522a61
- docs/source_adapter_contribution_guide.md: refreshed src-2dcb1b670f7ac406c7e6d54fd6332a535b7f1225ab75dca7fb06212479ec1678 -> src-094e9d10a317eb4efa40bdeb1e525060fb22edd6abf6dbb0b8ae8cd246869e85
- src/hocrgen/source_ops.py: refreshed src-7645c1735bb21b0b6b7f6c227c03bb045ad98e2453d405184932da2c1d7979fd -> src-7e2f679f5557dee086fc19ff6c83f7fcddf531da2febcba8dbe3a593b3105622
- src/hocrgen/config/sources.yaml: refreshed src-9103f65e8911cedc94beac8cab6290547aad7721595c7e459383204ccb44adcc -> src-0d6db30bef37a10be775ab2bf1b554839a9b005d6081dbacd7fb9ade64aabb3e
- src/hocrgen/fetchers/synthetic.py: refreshed src-e124b899edb8e843109b1a9f0ae9a2f1f973e1ee97f82f666876e4f355be9229 -> src-e023aa5fcc55f0f81105db430f70d12f1be4fe8782e10c3538c1ad4574229e1b
- docs/synthetic_asset_contribution_guide.md: refreshed src-6f9782d7d662b67b7782bcc206cfe769357909c3c00f7fb7a10c08f58ac6e784 -> src-8cbc22a9c90e1cc206141737ee70aff22afc792fe582371896784447f9aab814
Stale ingest summary: processed=27 succeeded=27 failed=0 skipped=0
Final freshness: total=79 unchanged=52 changed=0 missing=0 unsupported=0 historical=27
Next: splendor wiki status

$ splendor source freshness
Source freshness preview
Summary: total=79 unchanged=52 changed=0 missing=0 unsupported=0 historical=27
...
Final output listed refreshed active source manifests as unchanged and older source ids as historical.

$ splendor query "F6f"
Query: F6f
Summary: No matches found for "F6f".
Matches:

$ splendor query "Integrate a larger validated hocrsyngen batch"
Query: Integrate a larger validated hocrsyngen batch
Summary: Found 79 matching records. Best match: "hocrgen synthetic spinout plan amendment by chatgpt" (wiki/sources/src-e185635b13b3c908dfbaa711ed6afa334f354ead32d827fb68cab2e561c19a25.md).
Matches:
1. hocrgen synthetic spinout plan amendment by chatgpt [source-summary]
   Path: wiki/sources/src-e185635b13b3c908dfbaa711ed6afa334f354ead32d827fb68cab2e561c19a25.md
2. hocrgen synthetic spinout plan amendment by gemini 1 [source-summary]
   Path: wiki/sources/src-7ae422c3690537954e41bddc048cc5c17629be8d76b1621f1f6fbcbeabb6bd9d.md
3. gemini review [source-summary]
   Path: wiki/sources/src-2a426a9848b5f52dbe77701d7ee18f5c515f3d6093ed8f18c0b02c8cb8ce8e13.md
4. pre alpha freeze plan [source-summary]
   Path: wiki/sources/src-0d280c17bdc9daee7b0acc4c01972a171ee24de5178b149874b0aec524ef0376.md
5. synthetic asset contribution guide [source-summary]
   Path: wiki/sources/src-6f9782d7d662b67b7782bcc206cfe769357909c3c00f7fb7a10c08f58ac6e784.md
6. hocrgen synthetic spinout plan amendment by gemini 2 [source-summary]
   Path: wiki/sources/src-1973d8ec01bb4e636ad2308ef9512037f062bd8c132da3017859e12fa257b379.md
7. HeOCR hocrgen long term roadmap [source-summary]
   Path: wiki/sources/src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32.md
8. README [source-summary]
   Path: wiki/sources/src-6cd7017ff09d2b3301e01611897211da36f013848bf2da840f5400f47caf7d9b.md
9. chatgpt review [source-summary]
   Path: wiki/sources/src-e41e11ee9c19a651f285b6ec36b0652f853bf66e730eb221c0f7afd315681103.md
10. .agent plan [source-summary]
   Path: wiki/sources/src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696.md
...
12. HeOCR hocrgen long term roadmap [source-summary]
   Path: wiki/sources/src-9f2cb4da3079d49d0107ebe680916d807f23abd7332e64116f07881c3ad9fdb2.md
...
16. .agent plan [source-summary]
   Path: wiki/sources/src-d0ffed432c58784f5b985ef8cb718ad6f2cbc2acc2a3be1f356d438f1ce0a512.md
...
Next: splendor file-answer --from-last-query --title 'Integrate a larger validated hocrsyngen batch'

$ splendor brief --agent-context "Continue hocrgen roadmap work after F6e"
Agent context
Goal: Continue hocrgen roadmap work after F6e
Work context:
Suggested next:
- [medium/work-thread] Review pr #72: F6a: Define post-F5 public beta closure roadmap target=- url=https://github.com/HeOCR/hocrgen/pull/72
- [medium/work-thread] Review pr #76: F6e: Close source-depth and composition readiness with real public-profile evidence target=- url=https://github.com/HeOCR/hocrgen/pull/76
- [medium/work-thread] Review pr #43: F1a: Define beta-scale trial plan and Splendor workspace target=- url=https://github.com/HeOCR/hocrgen/pull/43
- [medium/work-thread] Review pr #70: F5c: Close public beta readiness blocker sequencing and repo-owned handoff gaps target=- url=https://github.com/HeOCR/hocrgen/pull/70
- [medium/git-context] Review commit 9ba50e5: F6e: Close source-depth and composition readiness with real public-profile evidence target=9ba50e5
Git context: branch=HEAD head=9ba50e5 base=origin/main merge_base=9ba50e5075c14178c10de1a65ba93b0a904f0fda
Recent issues and PRs:
- pr #72 [merged] score=93: F6a: Define post-F5 public beta closure roadmap (https://github.com/HeOCR/hocrgen/pull/72)
- pr #76 [merged] score=78: F6e: Close source-depth and composition readiness with real public-profile evidence (https://github.com/HeOCR/hocrgen/pull/76)
- pr #43 [merged] score=75: F1a: Define beta-scale trial plan and Splendor workspace (https://github.com/HeOCR/hocrgen/pull/43)
- pr #70 [merged] score=75: F5c: Close public beta readiness blocker sequencing and repo-owned handoff gaps (https://github.com/HeOCR/hocrgen/pull/70)
- pr #54 [merged] score=60: F1b4: Expand NLI runnable/cached source depth before F1c execution (https://github.com/HeOCR/hocrgen/pull/54)
Recent commits:
- 9ba50e5 score=99: F6e: Close source-depth and composition readiness with real public-profile evidence
- bf47c88 score=56: F4b: Add hocrsyngen manifest synthetic input
- e6df5a7 score=56: F6a: Define post-F5 public beta closure roadmap (#72)
Files to read first:
- docs/HeOCR_hocrgen_long_term_roadmap.md
- src/hocrgen/config/public_beta.yaml
- src/hocrgen/data/benchmark/benchmark_v1/reference_manifest.json
- CONTRIBUTING.md
- README.md
...
Next actions:
- Review pr #72: F6a: Define post-F5 public beta closure roadmap
- Review pr #76: F6e: Close source-depth and composition readiness with real public-profile evidence
- Review pr #43: F1a: Define beta-scale trial plan and Splendor workspace
- Review pr #70: F5c: Close public beta readiness blocker sequencing and repo-owned handoff gaps
- Review commit 9ba50e5: F6e: Close source-depth and composition readiness with real public-profile evidence
- Run `splendor wiki suggest <source-id>` for ingested sources missing synthesis follow-up.
- Review draft, stale, contested, or machine-generated synthesis pages.
- Open the top matching wiki or planning records for the stated goal.
- Read the top authority docs before changing planning-heavy behavior.

$ splendor suggest-next "Continue hocrgen roadmap work from current main"
Suggested next actions
Goal: Continue hocrgen roadmap work from current main
Work actions:
1. [medium/work-thread] Review pr #72: F6a: Define post-F5 public beta closure roadmap target=- url=https://github.com/HeOCR/hocrgen/pull/72
   Reason: Planning notation
2. [medium/work-thread] Review pr #43: F1a: Define beta-scale trial plan and Splendor workspace target=- url=https://github.com/HeOCR/hocrgen/pull/43
   Reason: Planning notation
3. [medium/work-thread] Review pr #70: F5c: Close public beta readiness blocker sequencing and repo-owned handoff gaps target=- url=https://github.com/HeOCR/hocrgen/pull/70
   Reason: Planning notation
4. [medium/work-thread] Review pr #45: F4a: Record synthetic spinout architecture target=- url=https://github.com/HeOCR/hocrgen/pull/45
   Reason: Planning notation
5. [medium/git-context] Review commit 5bbbc17: F2a: Define benchmark ground-truth guidelines (#60) target=5bbbc17
   Reason: Recent git context relevant to the stated goal.
6. [medium/git-context] Review commit 9ba50e5: F6e: Close source-depth and composition readiness with real public-profile evidence target=9ba50e5
   Reason: Recent git context relevant to the stated goal.
7. [medium/git-context] Review commit bf47c88: F4b: Add hocrsyngen manifest synthetic input target=bf47c88
   Reason: Recent git context relevant to the stated goal.
8. [medium/authority] Read authority doc docs/HeOCR_hocrgen_long_term_roadmap.md target=docs/HeOCR_hocrgen_long_term_roadmap.md
   Reason: roadmap/current/current/inferred-authority/curated: Inferred roadmap or planning authority from a conventional docs path. Detected by filename/path heuristic over a curated source.
Authority docs:
- docs/HeOCR_hocrgen_long_term_roadmap.md [roadmap/current/current/inferred-authority] score=248 HeOCR / hocrgen Long-Term Roadmap and Milestone Plan
- docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_gemini_2.md [roadmap/current/current/inferred-authority] score=226 Amendment to the Strategic Roadmap for Hocrgen: Decoupling and Advancing Believable Synthetic Handwriting Generation
- README.md [current-authority/current/current/inferred-authority] score=215 hocrgen
- docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_chatgpt.md [roadmap/current/current/inferred-authority] score=207 Amendment suggestion: spin out synthetic Hebrew OCR/HTR document generation into a separate project
- .agent-plan.md [roadmap/current/current/inferred-authority] score=189 Agent Plan
...
Maintenance notes:
- Wiki review-needed pages and missing synthesis are maintenance state, not default active human tasks.

$ splendor query "Start the next hocrsyngen provider-gate implementation work"
Query: Start the next hocrsyngen provider-gate implementation work
Summary: Found 40 matching records. Best match: "hocrgen synthetic spinout plan amendment by gemini 2" (wiki/sources/src-1973d8ec01bb4e636ad2308ef9512037f062bd8c132da3017859e12fa257b379.md).
Matches:
1. hocrgen synthetic spinout plan amendment by gemini 2 [source-summary]
   Path: wiki/sources/src-1973d8ec01bb4e636ad2308ef9512037f062bd8c132da3017859e12fa257b379.md
2. pre alpha freeze plan [source-summary]
   Path: wiki/sources/src-0d280c17bdc9daee7b0acc4c01972a171ee24de5178b149874b0aec524ef0376.md
3. .agent plan [source-summary]
   Path: wiki/sources/src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696.md
4. hocrgen synthetic spinout plan amendment by gemini 1 [source-summary]
   Path: wiki/sources/src-7ae422c3690537954e41bddc048cc5c17629be8d76b1621f1f6fbcbeabb6bd9d.md
5. synthetic asset contribution guide [source-summary]
   Path: wiki/sources/src-6f9782d7d662b67b7782bcc206cfe769357909c3c00f7fb7a10c08f58ac6e784.md
...
13. .agent plan [source-summary]
   Path: wiki/sources/src-d0ffed432c58784f5b985ef8cb718ad6f2cbc2acc2a3be1f356d438f1ce0a512.md
...
32. source ops [source-summary]
   Path: wiki/sources/src-7e2f679f5557dee086fc19ff6c83f7fcddf531da2febcba8dbe3a593b3105622.md
...
Next: splendor file-answer --from-last-query --title 'Start the next hocrsyngen provider-gate implementation answer'

$ git status --short --branch
## HEAD (no branch)
 M state/manifests/sources/src-0561b14d6a9f09cc3fcd3824f1a0b8885e65e52b607e8a5cadbdd6fa7f33a17d.json
 M state/manifests/sources/src-0d280c17bdc9daee7b0acc4c01972a171ee24de5178b149874b0aec524ef0376.json
 M state/manifests/sources/src-1973d8ec01bb4e636ad2308ef9512037f062bd8c132da3017859e12fa257b379.json
 M state/manifests/sources/src-2dcb1b670f7ac406c7e6d54fd6332a535b7f1225ab75dca7fb06212479ec1678.json
 M state/manifests/sources/src-44135f2c3655e8e66a22fe614200465d4ac3236e54dbbc56510dd01b09c03696.json
 M state/manifests/sources/src-45b84be09c1d6cc3524d1b4047af8e013fd0a855abd750df7d6759466c721855.json
 M state/manifests/sources/src-4a98a45e36a5b81caf8469cf906a273d0b28e0ce04dbed48b3a503bd3902e755.json
 M state/manifests/sources/src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61.json
 M state/manifests/sources/src-6cd7017ff09d2b3301e01611897211da36f013848bf2da840f5400f47caf7d9b.json
 M state/manifests/sources/src-6f9782d7d662b67b7782bcc206cfe769357909c3c00f7fb7a10c08f58ac6e784.json
 M state/manifests/sources/src-7645c1735bb21b0b6b7f6c227c03bb045ad98e2453d405184932da2c1d7979fd.json
 M state/manifests/sources/src-7ae422c3690537954e41bddc048cc5c17629be8d76b1621f1f6fbcbeabb6bd9d.json
 M state/manifests/sources/src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32.json
 M state/manifests/sources/src-83f63fa5b1a448ac62b77c5b43dd15c78d21a2fa020d203622f16e17f34c0e10.json
 M state/manifests/sources/src-8ec8d8c7f652e9a55cd9d0ea8fb96420b1e8071c2f87680cdf02ccddfea6a246.json
 M state/manifests/sources/src-9103f65e8911cedc94beac8cab6290547aad7721595c7e459383204ccb44adcc.json
 M state/manifests/sources/src-971f32069b2f2c2611a2e217ff9c4df10168a170f44f43af473663bf0e3a9b72.json
 M state/manifests/sources/src-a586b8dfff3260278e7afa8f70497c6c3d99644a2632af8dd2548cf23003d3c2.json
 M state/manifests/sources/src-be89457a63cbe7a028944287494a0cecc0c6c8f5da3d49f0050d48b6b6f8fb50.json
 M state/manifests/sources/src-c9bf621a4a08694fff9fbbc2315b560dd7b5888034e37467b9d1c5a49f46393f.json
 M state/manifests/sources/src-d35450808b548f78d689a33e3f28a788ebd93da5ee5e2296a60082db4906d6d2.json
 M state/manifests/sources/src-d4c2c30bdbf4d27cb63489e6c3f2045f1526dc1fcfeea0c516c8aff2eb5503f2.json
 M state/manifests/sources/src-d76cc18a7d533e5085d4cc98c81687ebe3492ca8cf1395e4bfd781ca4b3b92f0.json
 M state/manifests/sources/src-e124b899edb8e843109b1a9f0ae9a2f1f973e1ee97f82f666876e4f355be9229.json
 M state/manifests/sources/src-e185635b13b3c908dfbaa711ed6afa334f354ead32d827fb68cab2e561c19a25.json
 M state/manifests/sources/src-f017f2efcbbfa07f397c9930ea3793f5cb6533a420334227ebef033c388de1fb.json
 M state/manifests/sources/src-f947470a59c2a7839ec2b42d05af523c06e621e58b6e3e3d9f07c2fa3f790f35.json
 M wiki/index.md
 M wiki/log.md
?? state/manifests/sources/src-094e9d10a317eb4efa40bdeb1e525060fb22edd6abf6dbb0b8ae8cd246869e85.json
?? state/manifests/sources/src-0bfd85d7c981ae45f388c1438259278f2aaae8e958de18f4fc3efa7a28345456.json
?? state/manifests/sources/src-0c27f7acefdf9bf5d8869396ffe458d04a688dc09c9f53832994cafa20522a61.json
?? state/manifests/sources/src-0d6db30bef37a10be775ab2bf1b554839a9b005d6081dbacd7fb9ade64aabb3e.json
?? state/manifests/sources/src-21c2f369e5c9fbdbf231e21b54ed3187f87144b8e592ce17a01eb79c7c909448.json
?? state/manifests/sources/src-2b6c37ab98effe110e15c5a99f5b39643d578c0650285919d56f0eebf4a7cd9c.json
?? state/manifests/sources/src-320e5722f67ded6445ac1f19234691ed35ee5eda5fe22579044385aa37c3f84e.json
...
?? wiki/sources/src-d0ffed432c58784f5b985ef8cb718ad6f2cbc2acc2a3be1f356d438f1ce0a512.md
?? wiki/sources/src-e023aa5fcc55f0f81105db430f70d12f1be4fe8782e10c3538c1ad4574229e1b.md
?? wiki/sources/src-ebfb17ec27fccc7e3973c3ebbad5191a64178e7178bf7ed46ae2b379ec6f5e9c.md
?? wiki/sources/src-f5957a324296c6a762c108f9f091632006ac2af4d103a8f4e36582bdc6f1fec6.md
?? wiki/sources/src-fea43f00e07588f21942f784ac2c3796535120d38a6294e79c9361dba2c3693b.md
```
