"""Tests for ConfirmView discord.ui.View."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from vcompany.bot.views.confirm import ConfirmView


class TestConfirmView:
    """ConfirmView provides confirm/cancel buttons with user restriction."""

    def test_has_confirm_and_cancel_buttons(self):
        """View has exactly two buttons: Confirm and Cancel."""
        view = ConfirmView()
        button_labels = [child.label for child in view.children]
        assert "Confirm" in button_labels
        assert "Cancel" in button_labels
        assert len(button_labels) == 2

    def test_timeout_defaults_to_30(self):
        """Default timeout is 30 seconds."""
        view = ConfirmView()
        assert view.timeout == 30.0

    def test_custom_timeout(self):
        """Timeout can be overridden."""
        view = ConfirmView(timeout=60.0)
        assert view.timeout == 60.0

    def test_initial_value_is_none(self):
        """value starts as None (no response yet)."""
        view = ConfirmView()
        assert view.value is None

    @pytest.mark.asyncio
    async def test_confirm_callback_sets_value_true(self):
        """Pressing Confirm sets value to True."""
        view = ConfirmView()
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        # Find and invoke the confirm button callback
        await view.confirm.callback(interaction)

        assert view.value is True
        interaction.response.send_message.assert_called_once_with(
            "Confirmed.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_cancel_callback_sets_value_false(self):
        """Pressing Cancel sets value to False."""
        view = ConfirmView()
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await view.cancel.callback(interaction)

        assert view.value is False
        interaction.response.send_message.assert_called_once_with(
            "Cancelled.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_interaction_check_allows_correct_user(self):
        """interaction_check allows the original invoker."""
        view = ConfirmView()
        view.interaction_user_id = 12345

        interaction = MagicMock()
        interaction.user.id = 12345

        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_blocks_other_user(self):
        """interaction_check blocks a different user."""
        view = ConfirmView()
        view.interaction_user_id = 12345

        interaction = MagicMock()
        interaction.user.id = 99999
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        result = await view.interaction_check(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_interaction_check_allows_all_when_no_restriction(self):
        """interaction_check allows any user when interaction_user_id is None."""
        view = ConfirmView()
        assert view.interaction_user_id is None

        interaction = MagicMock()
        interaction.user.id = 99999

        result = await view.interaction_check(interaction)
        assert result is True
