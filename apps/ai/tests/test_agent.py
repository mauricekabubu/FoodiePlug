from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.ai.services import agent


class GeminiBackendFallbackTests(SimpleTestCase):
    @override_settings(GEMINI_FALLBACK_MODEL="gemini-3.6-flash")
    def test_retries_on_server_error_status_and_response_status(self):
        response = SimpleNamespace(candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=[
                SimpleNamespace(text="Hello", function_call=None, thought=False),
            ])),
        ])
        types = SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: SimpleNamespace(**kwargs),
            AutomaticFunctionCallingConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        )

        code_failure = RuntimeError("server error")
        code_failure.code = 500
        response_failure = RuntimeError("server error")
        response_failure.response = SimpleNamespace(status_code=503)

        failures = (code_failure, response_failure)

        for failure in failures:
            status = getattr(failure, "code", None) or failure.response.status_code
            with self.subTest(status=status):
                generate_content = mock.Mock(side_effect=[failure, response])
                client = SimpleNamespace(
                    models=SimpleNamespace(generate_content=generate_content),
                )
                backend = agent.GeminiBackend(
                    api_key="test-key",
                    model="gemini-3.8-flash",
                )

                with (
                    mock.patch.object(backend, "_get_client", return_value=client),
                    mock.patch.object(
                        agent.importlib,
                        "import_module",
                        return_value=types,
                    ),
                ):
                    result = backend.generate(
                        system_instruction="",
                        entries=[],
                        tool_declarations=[],
                    )

                self.assertEqual(result.text, "Hello")
                self.assertEqual(
                    [call.kwargs["model"] for call in generate_content.call_args_list],
                    ["gemini-3.8-flash", "gemini-3.6-flash"],
                )