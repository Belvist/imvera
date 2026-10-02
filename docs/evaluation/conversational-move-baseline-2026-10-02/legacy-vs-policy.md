# Dialogue comparison — captured text

Suite: `conversational-moves-v1` / `0b79c38ca190e5a2d0de9bcc2d7a3535138296d122e6e2218b82af58d222808d`.

Comparable cases: **15/15**. Missing cases remain NOT_RUN.

This is a transcript comparison, not a measured superiority or warmth/MOS score.

A: IMVERA-legacy / `09cff20133fcf77b32bf9b32357ee0dd1922daa2` / text / 2026-10-02T19:09:29.010018+00:00.
Evidence: canonical SDK replay; runtime: `{'git_dirty': True, 'python': '3.12.14', 'platform': 'Linux', 'audio': 'NOT_RUN', 'live_act_inference': 'NOT_RUN', 'human_warmth_rating': 'NOT_RUN', 'understanding_path': 'SDK TurnUnderstandingV2.resolve; CallActor producer NOT_RUN', 'delivery': 'SIMULATED_COMPLETED; transport/audible delivery NOT_RUN', 'router': {'action_policy.mode': 'legacy', 'action_policy.mode_raw': 'legacy', 'action_policy.cutover_enabled': False, 'action_policy.soft_percent': 0, 'action_policy.policy_version': 'action-policy-phase1-v9', 'action_policy.frozen_policy_sha': '254f0baed11ba7913d276c50ca7bd574778f19a5', 'action_policy.decision_scope': 'conversation_scheduler', 'IMVERA_ACTION_POLICY_MODE': 'legacy', 'IMVERA_ACTION_POLICY_CUTOVER_ENABLED': '0', 'IMVERA_ACTION_POLICY_SOFT_PERCENT': '0'}, 'coverage_ladder_enabled': False, 'speech_day': '0', 'speech_hour': '10', 'act_head_requested': 'v2', 'source_sha256': {'packages/dialogue_engine/__init__.py': '33797ccc6c5df4ebefa56a272b621503353f0b1e698f9e21f208f5ffd83911ed', 'packages/dialogue_engine/action_policy/__init__.py': '8be0a5dc7dabeaf87d7ef576e5ec0727ff95b3dd7050b8d6e30129506c6018c3', 'packages/dialogue_engine/action_policy/actions.py': '95030b08c4a372d35bd7268491d0a2e65247af21c4b8c1984671c8804d63556b', 'packages/dialogue_engine/action_policy/bridge.py': '097fc65cc69224266511c2c0ec5cb067ac8667eb20b37de76dce29b9ce8afb91', 'packages/dialogue_engine/action_policy/constraints.py': '3a669aeb959f50da77bc0d7a49672800a1abce4acb989f056271ac730fe90bce', 'packages/dialogue_engine/action_policy/features.py': 'b2e5576df7b099ce1aa3ef65cb2884333510fa15a20e471b1db1aeebc24f2897', 'packages/dialogue_engine/action_policy/mandatory.py': '2a08a110a3138bc895567e83c82b3954c110dae03279fd49296a770982e483b1', 'packages/dialogue_engine/action_policy/need_value.py': '3cd09ea178c59a1a4e8aa6df74f75092dcf12aa3d743ee22d2a5aa77aae51940', 'packages/dialogue_engine/action_policy/needs.py': 'bde922a3f330fbb8a5610430993f1789492f9b3eb0984e60d3f7f29ad9484e7e', 'packages/dialogue_engine/action_policy/policy.py': '64ea7e5dc00799bc8408693fd9744c92b20ba68ad41a4558b77e39a371d64184', 'packages/dialogue_engine/action_policy/scorer.py': 'b731fe564cd20776cfeb5d5a212cf8cc8db1c3294441ed660f2f84387761157d', 'packages/dialogue_engine/action_policy/semantic_signals.py': 'ba1e77a90e8f06ffce9bc1b579c7cffa9eeaa27fce55d53cea074c15c9ab06fc', 'packages/dialogue_engine/action_policy/snapshot.py': '9a7e60ab6757485f5b739a37c4df4512a74d844d45092bd5392d07bd90ce0349', 'packages/dialogue_engine/action_policy_shadow.py': '18860d20c5c2c6f8b1594532ace1d8256e47bbdd6c3b377ea6851e8650605ae9', 'packages/dialogue_engine/action_policy_shadow_buffer.py': 'f782e16ebc13e4bfc10390f43bf932787281a17dae349eee93355b18eb816bd3', 'packages/dialogue_engine/action_policy_shadow_config.py': '19e39c0cbf83bc5ddb79274ec43bf9c27a74f2c15232455f01d01781b321637c', 'packages/dialogue_engine/caller_memory.py': '338b2a29f7bd58d76a9f5af818b61e67538e03ed508476f7f52f427ff0f58f15', 'packages/dialogue_engine/check_path.py': 'd789933e0c5d61d3cf3de3f3ffca15c27d452a9ed5f11d50eaba7ef819877ad0', 'packages/dialogue_engine/context.py': 'a0d75e74e534c3c7161a912e7030dcaf4af6a4034714f2693e3bfd29b5e1f3f7', 'packages/dialogue_engine/contextual_interpreter.py': '7ed5609d8a28186396a39bdbe1efeafefdb93c26a1463170e6c878f1221be892', 'packages/dialogue_engine/conversation_policy.py': '85f268aaf349c3b8c95daf2d52b705311efee9f945a857caa5ca4194ac56c98f', 'packages/dialogue_engine/corpus/__init__.py': '413398f2bf2945f7ce5b71a2503d36491af44dc65935d8e7c61dcfa9d26733a1', 'packages/dialogue_engine/corpus/families.py': 'a380af8d991eec5e5196b7d71d36fc3b531604a98e3e88ee18589b8673214c12', 'packages/dialogue_engine/corpus/generator.py': '80dbf8e0722ea19dad9331e68e657a25cbb707f9de7f348e06354610e310e379', 'packages/dialogue_engine/corpus/lexicon.py': '0aa4cd2de685ae31c0b37794858ea78873b670c612f1183bc365de39e55a172d', 'packages/dialogue_engine/corpus/report.py': 'cb93dba860bd3693859f6d630c0f992f2e06e197061b0f4f92d81e8067246c56', 'packages/dialogue_engine/corpus/runner.py': '316850afc3ae75bfc3eea7c6f3700b6c655df46d34468c9d3e95efb9fbb8d17a', 'packages/dialogue_engine/corpus/schema.py': '4517491f72bd830351c848ff6b90fcc60f3b58096fa425c2ca3ca7d90045e12c', 'packages/dialogue_engine/coverage.py': '05db5f96e9a56278e3c52f4aacee486b8162a034cc97120b31a07a8adc2cc34e', 'packages/dialogue_engine/decision_router.py': '59789d3d0a07d31d56a7a4bfd6fd83839cae1dd3c2a5b1733fd9626e96a1a620', 'packages/dialogue_engine/delivery/__init__.py': 'bf3bd2d7d99b9a9664f9ed8ef036bccc91612faabf71f55869be3192f828d7b8', 'packages/dialogue_engine/delivery/decision.py': 'e2b799fa94779b82eba8c311974e951f45a326e5b928ce84f00ce915f74cf61c', 'packages/dialogue_engine/delivery/dispatcher.py': 'e684cc012e42931edd941a76a2fc9c7e075d91840b1117b60c3f1024f216bc76', 'packages/dialogue_engine/delivery/outbox.py': 'e85201af8ad49d5cb173d509a245c5ec44935b77bb2055b0ada36873a0bc53c9', 'packages/dialogue_engine/delivery/scope.py': 'ebe5474b5a1d0c48490113b4bb67744c0f6d0b97c0d6bb3c9682449d6231f59b', 'packages/dialogue_engine/deterministic_mission.py': '020084de02dbfc4b7ffd3aa00e1870837a75528d210f1b47ed67f60d9df0e201', 'packages/dialogue_engine/discourse.py': 'acaac2c83ca9cb52657aa7efb81c387be4bd8d5c60452244ce00a6437be41d60', 'packages/dialogue_engine/effects.py': '5eb5a6777fae40d05c8f6ad71c3260cf3b94a10b157df990bdb9be93d5700f7a', 'packages/dialogue_engine/engine.py': '42e3abadd22e20174c661c0e530ba447999f2e1d54e50c348c46793bb9ace3e2', 'packages/dialogue_engine/events.py': 'cad284bc132904f62c0469eb4e36688a08b4a5c96ff1b2bbd58cbb8720588f05', 'packages/dialogue_engine/evidence_invariant.py': '888b151de82dbb71498d16e0e4b4f7f1b16b354df48cb5687799df7349f27537', 'packages/dialogue_engine/fast_interpreter.py': 'c7a0e64979d78734bdace0bcdffaee6c066405dfc37eb47198daacf3d3d93619', 'packages/dialogue_engine/invariants.py': '736a1d8920c8eee00bca3f239f625b09c9e3975473b850bcd8cdc04173611a97', 'packages/dialogue_engine/issue_memory.py': '82259e1256a0016d7d96b9fbd31882dd84def704f3b90e8dbd00a52b8491a373', 'packages/dialogue_engine/issue_mention_extract.py': '9094a1f5dd3b98e969521c6cfb591ede185aa73584ffc13a6b48405aeca7c29b', 'packages/dialogue_engine/mission.py': 'f2d6be3b6f3eb33a213d9c2d3a1d6ce95d574b53b58e83ae1af688abf16f554d', 'packages/dialogue_engine/mission_context.py': '8ddca87c0cf653d355261499edbb0405331e98e59b8f195ef5c8949553c0a91b', 'packages/dialogue_engine/mission_flow.py': '70e391a7e5fb0e9f59d067ba2377bf515743176f311d3aff144b0e4b55217b66', 'packages/dialogue_engine/mission_grounding.py': '9e8b6f6087fe35acb591d52cc02b526c7f3f8b1b7cd6c39eb0f384d20f07c725', 'packages/dialogue_engine/mission_result.py': 'f4c86324eb1c4b67d5b6b97dc2236982b3d05928a27bffd3111201ee8ba11f31', 'packages/dialogue_engine/mission_seed.py': '6f8eb078d0f767ea23698b19cb1aec5e74fbea253e42cdc781ab23769e31292c', 'packages/dialogue_engine/mission_understanding.py': '481f09c6fb4b293d3750ccf8763ffb20d2b21aa723c834ae35caccf1ad2376fc', 'packages/dialogue_engine/neuro/__init__.py': 'b0b66d5034bb53d918a6d150eef033c12430a190cc86ea1e77c6a9c9e2e6b56e', 'packages/dialogue_engine/neuro/interfaces.py': '275bfb267a98968c89e80369305ec738a904d53af16f7ab9d7d6da0a1fd04ad6', 'packages/dialogue_engine/neuro/paraphrase.py': 'fded910c68aa52454f612dd8ea45bc0903b519d0868483fa2c0e5ec93e47b450', 'packages/dialogue_engine/neuro/ranker.py': '446cbe11d5a7f5a8410c321739e065e9669c38efef95c6c6c55d66315278f51d', 'packages/dialogue_engine/neuro/shadow.py': 'd1fc57de57bc95fa25691290fbcb338599e9eaba40f5064a66099e6b7526064b', 'packages/dialogue_engine/persistence_projection.py': '6ad196234fc56fd445ef98eaaec5da76d4c479f7a2a725aa9b086602083ac00c', 'packages/dialogue_engine/policy.py': '5165f4d21d2d3d826042c481754a5bd922e82e353528f42ec8eb2a6c61e88043', 'packages/dialogue_engine/product/__init__.py': '3a2c9067ce9496340c0ebcc15d486a919ceb3ab879c259968967c887b41bf8b6', 'packages/dialogue_engine/product/issue_plans.py': '43b5ece7d559dbdad0b3fb67eefcba080d02f8ab4a619c124767fa1ac1d0aeae', 'packages/dialogue_engine/product/known.py': '2e5aa8e79782602ba830910e13b875ace5c61031e1f08aaf2d554c4b86f763e3', 'packages/dialogue_engine/product/planner.py': '344793d9634275599fa24d8f6f19332e5f40459ecc9eb8b6bc04ac1dee26eda5', 'packages/dialogue_engine/product/spoken.py': '58e8f94285d34ae19948d0e8af5153e5f0c3e795a13af72c387ad53538911aae', 'packages/dialogue_engine/proof_bundle.py': 'e5333fb2d26a3e870416c0f0e2c64900156736268c48c3e5bb5a8d6fa8f0ccff', 'packages/dialogue_engine/protocol/__init__.py': '31807ba233e4dc133afcc53ee2866bd6240878c7952aa273131ef41358861c80', 'packages/dialogue_engine/protocol/acts.py': '30b52cdb1eabc6e0fbee9263c28de97f3e820c3150f1e6589a03b1cf68701b72', 'packages/dialogue_engine/question_context.py': '9a528a0c5192528b91c490e61a4188ce521953a08bb61d8d03ff45cf2aec8327', 'packages/dialogue_engine/questions.py': '83dae7bbd33e0539e66b61ecad444f5dd26ad595bc82bd9ea324f7c598925e7e', 'packages/dialogue_engine/reducer.py': 'de2975546a3a2aaa1279235c84887e33638727fbc5299173cd7c521e75fc04d3', 'packages/dialogue_engine/reluctance.py': '94dd17519a036985a8dd3b42e39e682c54259e3c367bf9a14904be5bfdf8b963', 'packages/dialogue_engine/response_plan.py': '89079f85fa7fa9b424050ab39eaaf059ab4d791d776bc1310b3f5b2525e36253', 'packages/dialogue_engine/runtime.py': '1d842c9f598e262f84341614cbf24e8dfff9b7ad4ec24aed78d50b17ae19fcc0', 'packages/dialogue_engine/scenario_runner.py': '737da40deacc885b0db7c60e365baeb65eb6271f940f4da97670b290060be176', 'packages/dialogue_engine/semantic.py': 'e21faf6ce61ec865834f13afd331ab46ee289dcb99a42799c8465471793026e2', 'packages/dialogue_engine/semantic_kernel/__init__.py': '705be4d34b27a6b4949fcf64e609a59beaac77881688c2e56f025d011280d0b5', 'packages/dialogue_engine/semantic_kernel/clauses.py': '9758fef7b99c4493818718f8e28d831ca04c11bb2073816cb3c1143db8b7e770', 'packages/dialogue_engine/semantic_kernel/controls.py': '14203a23998936a0927659472d86b00a323f00c5273b6f15c522b8a19f1e6382', 'packages/dialogue_engine/semantic_kernel/information_gain.py': 'a738198d871a21a619a59742169d590e1ff41ce80686e47598184f806b6cbf38', 'packages/dialogue_engine/semantic_kernel/kernel.py': 'a77f74538db638cec117989590e22d6c80fc2b38275f93c442108ac8887b893c', 'packages/dialogue_engine/semantic_kernel/lexicon.py': 'bc2b30061490fababc96756aadc09f0a494b85184458ad0f7c4cbe43324a5314', 'packages/dialogue_engine/semantic_kernel/ml_fallback.py': 'c44bb02b80cd894b7ca34ca3517f45287d72e6a931ca5849093fc665ca93b3bb', 'packages/dialogue_engine/semantic_kernel/morphology.py': 'cf764319baee32e8cea65b4f29c5bdbdaf648de1002923e1abe65304f1bd514b', 'packages/dialogue_engine/semantic_kernel/observation_memory.py': '60d2c1021fb05e27dc632d5fbd68a997b547bcdd5e503e4856903b4c21346886', 'packages/dialogue_engine/semantic_kernel/reference_resolver.py': '06866c12f221513743a907230465a29562bd02f1c274d1b768cf4259e09f67c8', 'packages/dialogue_engine/semantic_kernel/relation_parser.py': '61fb2352a26603e8ca8c1c051467bd70ab5fb38b9a12b45f0efbd7356cfc966c', 'packages/dialogue_engine/semantic_kernel/span_parser.py': '4841b6cf965fce444cae7f1238a38daff390beb0aaf88330adccccccf59a0e79', 'packages/dialogue_engine/semantic_kernel/subject_resolver.py': 'f9d39c8fa31433693598172f3365e6bc2b7968b6ee8428ba1d78731ccf347d18', 'packages/dialogue_engine/semantic_kernel/types.py': '8ceab353583ea4fb0e7f9b4b9f47a0d0309333069148e9b3fb7e791142753b4a', 'packages/dialogue_engine/semantic_nlp/candidate.py': '6bf92e451450b236f672e23714b539efe994582d6e87f958d37ec317425f28a8', 'packages/dialogue_engine/semantic_nlp/goals.py': '2c5da8f563eb3fc1e2366c605b4dda6d0abbaff966c258803b5e808b9442ce0d', 'packages/dialogue_engine/semantic_nlp/labels.py': '16992765fc5f1d33c3ed3c4c7014b64c73c374c1db7c41f05155c6d017956873', 'packages/dialogue_engine/semantic_nlp/model.py': '59d1508e34c1ef097e5176548d0ddcc4166e455fbab7a7e9a394cbf175340403', 'packages/dialogue_engine/semantic_nlp/polarity.py': '279c1bc67a89ff6e8f7d1b0687b330a5755f8646e52ab6ebcd486ee8ab8ebfeb', 'packages/dialogue_engine/semantic_nlp/relation.py': '82cc1a87758411f2a69e86df018db8e577933b37bd80cb471ed34814293c939c', 'packages/dialogue_engine/semantic_nlp/warmup.py': 'ea0d5619fe0e9fff1a8d593b621648fa32337a1d0c0b9f6247718bee4cab90cf', 'packages/dialogue_engine/slotclf.py': 'c33fc998659c4c30b646a4b5cd80bd7d7761b340dc6308833f5d907f0503a42d', 'packages/dialogue_engine/speech_ledger.py': '173b4aa14d5f63969160e6fa75bc607227eaebd5bf7fac17e20247b15249cd32', 'packages/dialogue_engine/state.py': '47a7b1006356d96cef9c454a7ac58ddd62039ae97ecaa216afd42fd9afbaa0ae', 'packages/dialogue_engine/tinyllm.py': 'b5de105ac7319ed583d7bdc7145203b001bf42b3a171592cf402b2fbfb1c507c', 'packages/dialogue_engine/topic_tracker.py': 'f2d9ff0bdd56f35a0b39720ac9bd923057636b12d800ca6b76f09742d4215c6e', 'packages/dialogue_engine/turn_understanding.py': '8e9c972493564f8be7ccc033be3f8f137ea46330899c55adb9aded818081ca2d', 'packages/dialogue/session.py': '2e6e4029ff5f01c553ccb86b8ff7d3228acebcf178107e8560e0fea8453152cc', 'packages/voice_runtime/call_actor.py': 'd068de728b5d6df032cb7d3a765697f6c12af08c48c5bfb7a9443d7437b7b63e', 'tools/voice_lab/dialogue_comparison.py': '3a2a275d0b2b39101ee75f288b1dbfaee99231c1f1868a61dfc080a143d8a6bb'}}`.
B: IMVERA-policy / `09cff20133fcf77b32bf9b32357ee0dd1922daa2` / text / 2026-10-02T19:09:28.919403+00:00.
Evidence: canonical SDK replay; runtime: `{'git_dirty': True, 'python': '3.12.14', 'platform': 'Linux', 'audio': 'NOT_RUN', 'live_act_inference': 'NOT_RUN', 'human_warmth_rating': 'NOT_RUN', 'understanding_path': 'SDK TurnUnderstandingV2.resolve; CallActor producer NOT_RUN', 'delivery': 'SIMULATED_COMPLETED; transport/audible delivery NOT_RUN', 'router': {'action_policy.mode': 'policy', 'action_policy.mode_raw': 'policy', 'action_policy.cutover_enabled': True, 'action_policy.soft_percent': 0, 'action_policy.policy_version': 'action-policy-phase1-v9', 'action_policy.frozen_policy_sha': '254f0baed11ba7913d276c50ca7bd574778f19a5', 'action_policy.decision_scope': 'conversation_scheduler', 'IMVERA_ACTION_POLICY_MODE': 'policy', 'IMVERA_ACTION_POLICY_CUTOVER_ENABLED': '1', 'IMVERA_ACTION_POLICY_SOFT_PERCENT': '0'}, 'coverage_ladder_enabled': False, 'speech_day': '0', 'speech_hour': '10', 'act_head_requested': 'v2', 'source_sha256': {'packages/dialogue_engine/__init__.py': '33797ccc6c5df4ebefa56a272b621503353f0b1e698f9e21f208f5ffd83911ed', 'packages/dialogue_engine/action_policy/__init__.py': '8be0a5dc7dabeaf87d7ef576e5ec0727ff95b3dd7050b8d6e30129506c6018c3', 'packages/dialogue_engine/action_policy/actions.py': '95030b08c4a372d35bd7268491d0a2e65247af21c4b8c1984671c8804d63556b', 'packages/dialogue_engine/action_policy/bridge.py': '097fc65cc69224266511c2c0ec5cb067ac8667eb20b37de76dce29b9ce8afb91', 'packages/dialogue_engine/action_policy/constraints.py': '3a669aeb959f50da77bc0d7a49672800a1abce4acb989f056271ac730fe90bce', 'packages/dialogue_engine/action_policy/features.py': 'b2e5576df7b099ce1aa3ef65cb2884333510fa15a20e471b1db1aeebc24f2897', 'packages/dialogue_engine/action_policy/mandatory.py': '2a08a110a3138bc895567e83c82b3954c110dae03279fd49296a770982e483b1', 'packages/dialogue_engine/action_policy/need_value.py': '3cd09ea178c59a1a4e8aa6df74f75092dcf12aa3d743ee22d2a5aa77aae51940', 'packages/dialogue_engine/action_policy/needs.py': 'bde922a3f330fbb8a5610430993f1789492f9b3eb0984e60d3f7f29ad9484e7e', 'packages/dialogue_engine/action_policy/policy.py': '64ea7e5dc00799bc8408693fd9744c92b20ba68ad41a4558b77e39a371d64184', 'packages/dialogue_engine/action_policy/scorer.py': 'b731fe564cd20776cfeb5d5a212cf8cc8db1c3294441ed660f2f84387761157d', 'packages/dialogue_engine/action_policy/semantic_signals.py': 'ba1e77a90e8f06ffce9bc1b579c7cffa9eeaa27fce55d53cea074c15c9ab06fc', 'packages/dialogue_engine/action_policy/snapshot.py': '9a7e60ab6757485f5b739a37c4df4512a74d844d45092bd5392d07bd90ce0349', 'packages/dialogue_engine/action_policy_shadow.py': '18860d20c5c2c6f8b1594532ace1d8256e47bbdd6c3b377ea6851e8650605ae9', 'packages/dialogue_engine/action_policy_shadow_buffer.py': 'f782e16ebc13e4bfc10390f43bf932787281a17dae349eee93355b18eb816bd3', 'packages/dialogue_engine/action_policy_shadow_config.py': '19e39c0cbf83bc5ddb79274ec43bf9c27a74f2c15232455f01d01781b321637c', 'packages/dialogue_engine/caller_memory.py': '338b2a29f7bd58d76a9f5af818b61e67538e03ed508476f7f52f427ff0f58f15', 'packages/dialogue_engine/check_path.py': 'd789933e0c5d61d3cf3de3f3ffca15c27d452a9ed5f11d50eaba7ef819877ad0', 'packages/dialogue_engine/context.py': 'a0d75e74e534c3c7161a912e7030dcaf4af6a4034714f2693e3bfd29b5e1f3f7', 'packages/dialogue_engine/contextual_interpreter.py': '7ed5609d8a28186396a39bdbe1efeafefdb93c26a1463170e6c878f1221be892', 'packages/dialogue_engine/conversation_policy.py': '85f268aaf349c3b8c95daf2d52b705311efee9f945a857caa5ca4194ac56c98f', 'packages/dialogue_engine/corpus/__init__.py': '413398f2bf2945f7ce5b71a2503d36491af44dc65935d8e7c61dcfa9d26733a1', 'packages/dialogue_engine/corpus/families.py': 'a380af8d991eec5e5196b7d71d36fc3b531604a98e3e88ee18589b8673214c12', 'packages/dialogue_engine/corpus/generator.py': '80dbf8e0722ea19dad9331e68e657a25cbb707f9de7f348e06354610e310e379', 'packages/dialogue_engine/corpus/lexicon.py': '0aa4cd2de685ae31c0b37794858ea78873b670c612f1183bc365de39e55a172d', 'packages/dialogue_engine/corpus/report.py': 'cb93dba860bd3693859f6d630c0f992f2e06e197061b0f4f92d81e8067246c56', 'packages/dialogue_engine/corpus/runner.py': '316850afc3ae75bfc3eea7c6f3700b6c655df46d34468c9d3e95efb9fbb8d17a', 'packages/dialogue_engine/corpus/schema.py': '4517491f72bd830351c848ff6b90fcc60f3b58096fa425c2ca3ca7d90045e12c', 'packages/dialogue_engine/coverage.py': '05db5f96e9a56278e3c52f4aacee486b8162a034cc97120b31a07a8adc2cc34e', 'packages/dialogue_engine/decision_router.py': '59789d3d0a07d31d56a7a4bfd6fd83839cae1dd3c2a5b1733fd9626e96a1a620', 'packages/dialogue_engine/delivery/__init__.py': 'bf3bd2d7d99b9a9664f9ed8ef036bccc91612faabf71f55869be3192f828d7b8', 'packages/dialogue_engine/delivery/decision.py': 'e2b799fa94779b82eba8c311974e951f45a326e5b928ce84f00ce915f74cf61c', 'packages/dialogue_engine/delivery/dispatcher.py': 'e684cc012e42931edd941a76a2fc9c7e075d91840b1117b60c3f1024f216bc76', 'packages/dialogue_engine/delivery/outbox.py': 'e85201af8ad49d5cb173d509a245c5ec44935b77bb2055b0ada36873a0bc53c9', 'packages/dialogue_engine/delivery/scope.py': 'ebe5474b5a1d0c48490113b4bb67744c0f6d0b97c0d6bb3c9682449d6231f59b', 'packages/dialogue_engine/deterministic_mission.py': '020084de02dbfc4b7ffd3aa00e1870837a75528d210f1b47ed67f60d9df0e201', 'packages/dialogue_engine/discourse.py': 'acaac2c83ca9cb52657aa7efb81c387be4bd8d5c60452244ce00a6437be41d60', 'packages/dialogue_engine/effects.py': '5eb5a6777fae40d05c8f6ad71c3260cf3b94a10b157df990bdb9be93d5700f7a', 'packages/dialogue_engine/engine.py': '42e3abadd22e20174c661c0e530ba447999f2e1d54e50c348c46793bb9ace3e2', 'packages/dialogue_engine/events.py': 'cad284bc132904f62c0469eb4e36688a08b4a5c96ff1b2bbd58cbb8720588f05', 'packages/dialogue_engine/evidence_invariant.py': '888b151de82dbb71498d16e0e4b4f7f1b16b354df48cb5687799df7349f27537', 'packages/dialogue_engine/fast_interpreter.py': 'c7a0e64979d78734bdace0bcdffaee6c066405dfc37eb47198daacf3d3d93619', 'packages/dialogue_engine/invariants.py': '736a1d8920c8eee00bca3f239f625b09c9e3975473b850bcd8cdc04173611a97', 'packages/dialogue_engine/issue_memory.py': '82259e1256a0016d7d96b9fbd31882dd84def704f3b90e8dbd00a52b8491a373', 'packages/dialogue_engine/issue_mention_extract.py': '9094a1f5dd3b98e969521c6cfb591ede185aa73584ffc13a6b48405aeca7c29b', 'packages/dialogue_engine/mission.py': 'f2d6be3b6f3eb33a213d9c2d3a1d6ce95d574b53b58e83ae1af688abf16f554d', 'packages/dialogue_engine/mission_context.py': '8ddca87c0cf653d355261499edbb0405331e98e59b8f195ef5c8949553c0a91b', 'packages/dialogue_engine/mission_flow.py': '70e391a7e5fb0e9f59d067ba2377bf515743176f311d3aff144b0e4b55217b66', 'packages/dialogue_engine/mission_grounding.py': '9e8b6f6087fe35acb591d52cc02b526c7f3f8b1b7cd6c39eb0f384d20f07c725', 'packages/dialogue_engine/mission_result.py': 'f4c86324eb1c4b67d5b6b97dc2236982b3d05928a27bffd3111201ee8ba11f31', 'packages/dialogue_engine/mission_seed.py': '6f8eb078d0f767ea23698b19cb1aec5e74fbea253e42cdc781ab23769e31292c', 'packages/dialogue_engine/mission_understanding.py': '481f09c6fb4b293d3750ccf8763ffb20d2b21aa723c834ae35caccf1ad2376fc', 'packages/dialogue_engine/neuro/__init__.py': 'b0b66d5034bb53d918a6d150eef033c12430a190cc86ea1e77c6a9c9e2e6b56e', 'packages/dialogue_engine/neuro/interfaces.py': '275bfb267a98968c89e80369305ec738a904d53af16f7ab9d7d6da0a1fd04ad6', 'packages/dialogue_engine/neuro/paraphrase.py': 'fded910c68aa52454f612dd8ea45bc0903b519d0868483fa2c0e5ec93e47b450', 'packages/dialogue_engine/neuro/ranker.py': '446cbe11d5a7f5a8410c321739e065e9669c38efef95c6c6c55d66315278f51d', 'packages/dialogue_engine/neuro/shadow.py': 'd1fc57de57bc95fa25691290fbcb338599e9eaba40f5064a66099e6b7526064b', 'packages/dialogue_engine/persistence_projection.py': '6ad196234fc56fd445ef98eaaec5da76d4c479f7a2a725aa9b086602083ac00c', 'packages/dialogue_engine/policy.py': '5165f4d21d2d3d826042c481754a5bd922e82e353528f42ec8eb2a6c61e88043', 'packages/dialogue_engine/product/__init__.py': '3a2c9067ce9496340c0ebcc15d486a919ceb3ab879c259968967c887b41bf8b6', 'packages/dialogue_engine/product/issue_plans.py': '43b5ece7d559dbdad0b3fb67eefcba080d02f8ab4a619c124767fa1ac1d0aeae', 'packages/dialogue_engine/product/known.py': '2e5aa8e79782602ba830910e13b875ace5c61031e1f08aaf2d554c4b86f763e3', 'packages/dialogue_engine/product/planner.py': '344793d9634275599fa24d8f6f19332e5f40459ecc9eb8b6bc04ac1dee26eda5', 'packages/dialogue_engine/product/spoken.py': '58e8f94285d34ae19948d0e8af5153e5f0c3e795a13af72c387ad53538911aae', 'packages/dialogue_engine/proof_bundle.py': 'e5333fb2d26a3e870416c0f0e2c64900156736268c48c3e5bb5a8d6fa8f0ccff', 'packages/dialogue_engine/protocol/__init__.py': '31807ba233e4dc133afcc53ee2866bd6240878c7952aa273131ef41358861c80', 'packages/dialogue_engine/protocol/acts.py': '30b52cdb1eabc6e0fbee9263c28de97f3e820c3150f1e6589a03b1cf68701b72', 'packages/dialogue_engine/question_context.py': '9a528a0c5192528b91c490e61a4188ce521953a08bb61d8d03ff45cf2aec8327', 'packages/dialogue_engine/questions.py': '83dae7bbd33e0539e66b61ecad444f5dd26ad595bc82bd9ea324f7c598925e7e', 'packages/dialogue_engine/reducer.py': 'de2975546a3a2aaa1279235c84887e33638727fbc5299173cd7c521e75fc04d3', 'packages/dialogue_engine/reluctance.py': '94dd17519a036985a8dd3b42e39e682c54259e3c367bf9a14904be5bfdf8b963', 'packages/dialogue_engine/response_plan.py': '89079f85fa7fa9b424050ab39eaaf059ab4d791d776bc1310b3f5b2525e36253', 'packages/dialogue_engine/runtime.py': '1d842c9f598e262f84341614cbf24e8dfff9b7ad4ec24aed78d50b17ae19fcc0', 'packages/dialogue_engine/scenario_runner.py': '737da40deacc885b0db7c60e365baeb65eb6271f940f4da97670b290060be176', 'packages/dialogue_engine/semantic.py': 'e21faf6ce61ec865834f13afd331ab46ee289dcb99a42799c8465471793026e2', 'packages/dialogue_engine/semantic_kernel/__init__.py': '705be4d34b27a6b4949fcf64e609a59beaac77881688c2e56f025d011280d0b5', 'packages/dialogue_engine/semantic_kernel/clauses.py': '9758fef7b99c4493818718f8e28d831ca04c11bb2073816cb3c1143db8b7e770', 'packages/dialogue_engine/semantic_kernel/controls.py': '14203a23998936a0927659472d86b00a323f00c5273b6f15c522b8a19f1e6382', 'packages/dialogue_engine/semantic_kernel/information_gain.py': 'a738198d871a21a619a59742169d590e1ff41ce80686e47598184f806b6cbf38', 'packages/dialogue_engine/semantic_kernel/kernel.py': 'a77f74538db638cec117989590e22d6c80fc2b38275f93c442108ac8887b893c', 'packages/dialogue_engine/semantic_kernel/lexicon.py': 'bc2b30061490fababc96756aadc09f0a494b85184458ad0f7c4cbe43324a5314', 'packages/dialogue_engine/semantic_kernel/ml_fallback.py': 'c44bb02b80cd894b7ca34ca3517f45287d72e6a931ca5849093fc665ca93b3bb', 'packages/dialogue_engine/semantic_kernel/morphology.py': 'cf764319baee32e8cea65b4f29c5bdbdaf648de1002923e1abe65304f1bd514b', 'packages/dialogue_engine/semantic_kernel/observation_memory.py': '60d2c1021fb05e27dc632d5fbd68a997b547bcdd5e503e4856903b4c21346886', 'packages/dialogue_engine/semantic_kernel/reference_resolver.py': '06866c12f221513743a907230465a29562bd02f1c274d1b768cf4259e09f67c8', 'packages/dialogue_engine/semantic_kernel/relation_parser.py': '61fb2352a26603e8ca8c1c051467bd70ab5fb38b9a12b45f0efbd7356cfc966c', 'packages/dialogue_engine/semantic_kernel/span_parser.py': '4841b6cf965fce444cae7f1238a38daff390beb0aaf88330adccccccf59a0e79', 'packages/dialogue_engine/semantic_kernel/subject_resolver.py': 'f9d39c8fa31433693598172f3365e6bc2b7968b6ee8428ba1d78731ccf347d18', 'packages/dialogue_engine/semantic_kernel/types.py': '8ceab353583ea4fb0e7f9b4b9f47a0d0309333069148e9b3fb7e791142753b4a', 'packages/dialogue_engine/semantic_nlp/candidate.py': '6bf92e451450b236f672e23714b539efe994582d6e87f958d37ec317425f28a8', 'packages/dialogue_engine/semantic_nlp/goals.py': '2c5da8f563eb3fc1e2366c605b4dda6d0abbaff966c258803b5e808b9442ce0d', 'packages/dialogue_engine/semantic_nlp/labels.py': '16992765fc5f1d33c3ed3c4c7014b64c73c374c1db7c41f05155c6d017956873', 'packages/dialogue_engine/semantic_nlp/model.py': '59d1508e34c1ef097e5176548d0ddcc4166e455fbab7a7e9a394cbf175340403', 'packages/dialogue_engine/semantic_nlp/polarity.py': '279c1bc67a89ff6e8f7d1b0687b330a5755f8646e52ab6ebcd486ee8ab8ebfeb', 'packages/dialogue_engine/semantic_nlp/relation.py': '82cc1a87758411f2a69e86df018db8e577933b37bd80cb471ed34814293c939c', 'packages/dialogue_engine/semantic_nlp/warmup.py': 'ea0d5619fe0e9fff1a8d593b621648fa32337a1d0c0b9f6247718bee4cab90cf', 'packages/dialogue_engine/slotclf.py': 'c33fc998659c4c30b646a4b5cd80bd7d7761b340dc6308833f5d907f0503a42d', 'packages/dialogue_engine/speech_ledger.py': '173b4aa14d5f63969160e6fa75bc607227eaebd5bf7fac17e20247b15249cd32', 'packages/dialogue_engine/state.py': '47a7b1006356d96cef9c454a7ac58ddd62039ae97ecaa216afd42fd9afbaa0ae', 'packages/dialogue_engine/tinyllm.py': 'b5de105ac7319ed583d7bdc7145203b001bf42b3a171592cf402b2fbfb1c507c', 'packages/dialogue_engine/topic_tracker.py': 'f2d9ff0bdd56f35a0b39720ac9bd923057636b12d800ca6b76f09742d4215c6e', 'packages/dialogue_engine/turn_understanding.py': '8e9c972493564f8be7ccc033be3f8f137ea46330899c55adb9aded818081ca2d', 'packages/dialogue/session.py': '2e6e4029ff5f01c553ccb86b8ff7d3228acebcf178107e8560e0fea8453152cc', 'packages/voice_runtime/call_actor.py': 'd068de728b5d6df032cb7d3a765697f6c12af08c48c5bfb7a9443d7437b7b63e', 'tools/voice_lab/dialogue_comparison.py': '3a2a275d0b2b39101ee75f288b1dbfaee99231c1f1868a61dfc080a143d8a6bb'}}`.

## volunteered_four_facts

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, настроение спокойное, спала хорошо, сегодня пойду гулять.
A: Хорошо, поняла. Может, ещё что-то важное хотите рассказать — по здоровью или дома?
B: Хорошо, поняла. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Нет, больше ничего.
A: Спасибо, Тамара Юрьевна. На сегодня всё. Берегите себя.
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 3: До свидания.
A: До свидания, Тамара Юрьевна. Всего вам хорошего.
B: До свидания, Тамара Юрьевна. Всего вам хорошего.

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'GREEN'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'GREEN'}`; episodes: 0.

## daughter_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приехала, хорошо посидели.
A: Вы говорили: «дочь вчера приехала, хорошо посидели». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: Чай пили и фотографии смотрели.
A: Как вам сейчас, когда вы об этом рассказываете?
B: Понимаю.

Input 3: А потом вспоминали наши поездки.
A: Спасибо, что поделились. А как ваше самочувствие сегодня?
B: Понимаю.

Input 4: Я еще хотела рассказать про дачу.
A: Записала. Ещё что-то беспокоит?
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## yesterday_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Вчера ходила в парк и встретила подругу.
A: Вы говорили: «вчера ходила в парк и встретила подругу». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: Долго сидели на скамейке и разговаривали.
A: Как вам сейчас, когда вы об этом рассказываете?
B: Понимаю.

Input 3: Я рада была ее увидеть.
A: Спасибо, что поделились. А как ваше самочувствие сегодня?
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## open_user_question

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: А вы любите музыку?
A: Поняла. Что-то ещё важное есть?
B: Я Вера, голосовой помощник сервиса Амвера. Звоню, чтобы узнать, как вы себя чувствуете.

Input 2: Я часто слушаю старые песни.
A: Часто — поняла вас, записала. Спасибо, Тамара Юрьевна. Я записала: часто. На сегодня всё. Берегите себя.
B: Часто — поняла вас, записала. Сейчас это сильно беспокоит или уже терпимо?

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'PARTIAL', 'candidate_family_status': 'YELLOW'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## topic_switch

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приезжала.
A: Вы говорили: «дочь вчера приезжала». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: А лучше про огород расскажу.
A: Как вам сейчас, когда вы об этом рассказываете?
B: Понимаю.

Input 3: Помидоры уже собрала.
A: Спасибо, что поделились. А как ваше самочувствие сегодня?
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## return_to_topic

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приезжала.
A: Вы говорили: «дочь вчера приезжала». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: Сегодня я гуляла в парке.
A: Хорошо, поняла. Что-то ещё хотите сказать?
B: Понимаю.

Input 3: Вернемся к дочери, она фотографии привезла.
A: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## not_recalled

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Голова болит.
A: Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
B: Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?

Input 2: Не помню.
A: Понимаю, не будем угадывать. Сейчас голова болит сильно или терпимо?
B: Понимаю, не будем угадывать. Когда начала болеть голова — сегодня или раньше?

Input 3: Терпимо.
A: Поняла, сейчас терпимо. Может, ещё что-то важное хотите рассказать — по здоровью или дома?
B: Сейчас голова болит сильно или терпимо?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## ambiguous_reply

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Как-то не очень.
A: Что именно беспокоит?
B: Что именно беспокоит?

Input 2: Не знаю, как объяснить.
A: Скажите, что болит — голова, сердце, живот? Или что случилось?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 3: Ничего не болит, просто устала.
A: Понимаю. Устала — спасибо, что рассказали. Когда это началось — сегодня или раньше?
B: Понимаю. Устала — спасибо, что рассказали. Когда это началось — сегодня или раньше?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## self_correction

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, спала хорошо.
A: Записала. Подскажите, есть ли ещё что-то важное по здоровью или дома?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Нет, я перепутала, спала плохо.
A: Спасибо, что рассказали. На сегодня всё. Берегите себя.
B: На что жалуетесь?

Input 3: Часто просыпалась.
A: До свидания, Тамара Юрьевна. Всего вам хорошего.
B: Часто — спасибо, что рассказали. Сейчас это сильно беспокоит или уже терпимо?

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'YELLOW'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## barge_in

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Подождите, я еще не закончила.
A: Вы говорили: «подождите, я еще не закончила». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: Голова болит со вчера.
A: Головная боль — поняла вас, записала. А сейчас голова ещё болит или уже почти прошла?
B: Слышу вас: головная боль. А кроме этого — по самочувствию ничего не тревожит?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## slow_speech

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, но вчера долго не могла уснуть.
A: Поняла. Что-то ещё важное есть?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Сегодня спала нормально.
A: Спасибо, что рассказали. На сегодня всё. Берегите себя.
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'GREEN'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## symptom_inside_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Вчера с дочерью чай пили, а голова болит со вчера, сейчас сильная боль.
A: Жаль, что голова болит. А сейчас голова ещё болит или уже почти прошла?
B: Жаль, что голова болит. Сейчас голова болит сильно или терпимо?

Input 2: Да, сейчас тоже беспокоит.
A: Я вас слушаю. Кроме головной боли, сейчас есть что-то ещё необычное — сильная слабость, головокружение или тошнота?
B: Расскажите, пожалуйста, чуть подробнее про головная боль.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## refuse_one_question

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Не хочу отвечать про здоровье, давайте просто поговорим.
A: Записала. Подскажите, есть ли ещё что-то важное по здоровью или дома?
B: Понимаю.

Input 2: Внучка вчера приезжала.
A: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
B: Понимаю.

Input 3: Фотографии привезла.
A: Сейчас не получилось узнать, как у вас дела. До свидания.
B: Понимаю.

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'DECLINED', 'candidate_family_status': 'YELLOW'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'DECLINED', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## finish_entire_call

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Спасибо, не хочу больше разговаривать.
A: Поняла. Что-то ещё важное есть?
B: Понимаю.

Input 2: До свидания.
A: До свидания, Тамара Юрьевна. Всего вам хорошего.
B: До свидания, Тамара Юрьевна. Всего вам хорошего.

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'DECLINED', 'candidate_family_status': 'YELLOW'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'DECLINED', 'candidate_family_status': 'YELLOW'}`; episodes: 0.

## just_conversation

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Я просто поговорить хотела, жалоб нет.
A: Вы говорили: «я просто поговорить хотела, жалоб нет». Я вас слушаю. Хотите рассказать чуть подробнее?
B: Понимаю.

Input 2: Мне нравится рассказывать про сад.
A: Как вам сейчас, когда вы об этом рассказываете?
B: Понимаю.

Input 3: Розы в этом году красивые.
A: Спасибо, что поделились. А как ваше самочувствие сегодня?
B: Понимаю.

Input 4: И про соседку хотела рассказать.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

Changed response sequences: 15/15 comparable cases.
Human review of warmth, respect, accuracy and rhythm remains required.
