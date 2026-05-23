import unittest

from marketing_sandbox import (
    ActionSpace,
    ActionSpaceDefinitionError,
    ActionSpaceValidationError,
    StrategyAction,
)


def make_action(category="price", **changes):
    base = {
        "category": category,
        "summary": "Declare one bounded marketing move.",
        "reason": "The sandbox needs an action to validate.",
        "parameters": {"list_price": 49, "discount_rate": 0.1}
        if category == "price"
        else {},
        "product_claims": (),
    }
    base.update(changes)
    return StrategyAction(**base)


def make_action_space(**changes):
    base = {
        "allowed_product_claims": frozenset(
            {"trial_pack", "return_guarantee", "portable_bottle"}
        ),
        "parameter_limits": {
            "price": {
                "list_price": (0, 100),
                "discount_rate": (0, 0.3),
                "coupon_value": (0, 30),
            },
            "promotion": {"content_budget": (0, 5000)},
        },
        "parameter_options": {
            "positioning": {"lead_value": frozenset({"trust", "convenience"})},
            "product": {"offer_form": frozenset({"trial_pack", "starter_bundle"})},
            "promotion": {"content_format": frozenset({"review", "short_video"})},
        },
    }
    base.update(changes)
    return ActionSpace(**base)


class ActionSpaceTests(unittest.TestCase):
    def test_normal_validates_mixed_marketing_actions(self):
        space = make_action_space()
        actions = (
            make_action(
                "positioning",
                parameters={"lead_value": "trust"},
            ),
            make_action(
                "product",
                parameters={"offer_form": "trial_pack"},
                product_claims=("trial_pack", "portable_bottle"),
            ),
            make_action(),
            make_action(
                "promotion",
                parameters={"content_format": "review", "content_budget": 1800},
            ),
        )

        space.validate_actions(actions)

        self.assertIn("price.list_price: [0, 100]", space.describe())
        self.assertIn("product.offer_form: starter_bundle, trial_pack", space.describe())

    def test_boundary_accepts_one_enabled_category_without_extra_rules(self):
        space = ActionSpace(allowed_categories=frozenset({"channel"}))

        space.validate_action(
            make_action("channel", parameters={"path": "trusted_platform"})
        )

        self.assertIn("Allowed action categories: channel", space.describe())

    def test_boundary_accepts_numeric_parameters_on_inclusive_limits(self):
        space = make_action_space()

        space.validate_action(
            make_action(parameters={"list_price": 0, "discount_rate": 0})
        )
        space.validate_action(
            make_action(parameters={"list_price": 100, "discount_rate": 0.3})
        )

    def test_boundary_product_action_can_have_no_claims_when_none_are_declared(self):
        space = ActionSpace(allowed_categories=frozenset({"product"}))

        space.validate_action(
            make_action("product", parameters={"packaging_focus": "portable"})
        )

    def test_special_allows_approved_product_claims_and_offer_options(self):
        space = make_action_space()
        action = make_action(
            "product",
            parameters={"offer_form": "starter_bundle"},
            product_claims=("return_guarantee",),
        )

        space.validate_action(action)

        self.assertEqual(action.product_claims, ("return_guarantee",))

    def test_special_validates_multiple_declared_semantic_options(self):
        space = make_action_space()

        space.validate_action(
            make_action(
                "promotion",
                parameters={"content_format": ["review", "short_video"]},
            )
        )

    def test_special_strategy_actions_must_cover_allowed_categories(self):
        space = ActionSpace(
            allowed_categories=frozenset({"product", "price"}),
            allowed_product_claims=frozenset({"trial_pack"}),
            parameter_limits={"price": {"list_price": (0, 100)}},
        )

        space.validate_strategy_actions(
            (
                make_action("product", product_claims=("trial_pack",)),
                make_action("price", parameters={"list_price": 49}),
            )
        )

        with self.assertRaisesRegex(ActionSpaceValidationError, "missing: product"):
            space.validate_strategy_actions(
                (make_action("price", parameters={"list_price": 49}),)
            )

    def test_special_strategy_actions_reject_pause_or_noop_language(self):
        space = ActionSpace(allowed_categories=frozenset({"promotion"}))

        with self.assertRaisesRegex(ActionSpaceValidationError, "pause"):
            space.validate_strategy_actions(
                (
                    make_action(
                        "promotion",
                        summary="No action in this category this round.",
                    ),
                )
            )

    def test_special_keeps_descriptive_and_boolean_parameters_unbounded(self):
        space = make_action_space()

        space.validate_action(
            make_action(
                "retention",
                parameters={"member_program": True, "reminder_tone": "gentle"},
            )
        )

    def test_counterexample_rejects_unrecognized_action_category(self):
        space = make_action_space()

        with self.assertRaisesRegex(ActionSpaceValidationError, "outside the ActionSpace"):
            space.validate_action(make_action("finance"))

    def test_counterexample_rejects_unapproved_product_claim(self):
        space = make_action_space()

        with self.assertRaisesRegex(
            ActionSpaceValidationError, "unapproved product claims"
        ):
            space.validate_action(
                make_action("product", product_claims=("medical_cure",))
            )

    def test_counterexample_rejects_unbounded_numeric_action_parameter(self):
        space = make_action_space()

        with self.assertRaisesRegex(ActionSpaceValidationError, "needs an ActionSpace limit"):
            space.validate_action(
                make_action("channel", parameters={"budget_share": 0.5})
            )

    def test_counterexample_rejects_unsupported_semantic_option(self):
        space = make_action_space()

        with self.assertRaisesRegex(ActionSpaceValidationError, "unsupported options"):
            space.validate_action(
                make_action("positioning", parameters={"lead_value": "status"})
            )

    def test_counterexample_rejects_disabled_category_rules_in_configuration(self):
        with self.assertRaisesRegex(ActionSpaceDefinitionError, "disabled categories"):
            ActionSpace(
                allowed_categories=frozenset({"price"}),
                parameter_limits={"promotion": {"content_budget": (0, 100)}},
            )

    def test_limit_dense_action_space_keeps_categories_limits_and_options_separate(self):
        space = make_action_space(
            parameter_options={
                "positioning": {
                    f"message_axis_{index}": frozenset(
                        {f"trust_{index}", f"ease_{index}"}
                    )
                    for index in range(25)
                },
                "product": {
                    "offer_form": frozenset(
                        {"trial_pack", "starter_bundle", "refill_pack", "gift_box"}
                    )
                },
            },
            parameter_limits={
                "price": {f"coupon_value_{index}": (0, 30) for index in range(30)}
            },
        )
        actions = tuple(
            make_action(
                "price",
                parameters={f"coupon_value_{index}": index % 31},
            )
            for index in range(30)
        ) + (
            make_action(
                "positioning",
                parameters={"message_axis_24": "ease_24"},
            ),
            make_action(
                "product",
                parameters={"offer_form": "gift_box"},
                product_claims=("trial_pack",),
            ),
        )

        space.validate_actions(actions)

        description = space.describe()
        self.assertIn("price.coupon_value_29: [0, 30]", description)
        self.assertIn("positioning.message_axis_24: ease_24, trust_24", description)


if __name__ == "__main__":
    unittest.main()
