"""Fail-closed placeholder for the optional macro-news LLM extractor."""

class MacroNewsLLMExtractor:
    def __init__(self, *args, **kwargs):
        self.metrics = {"extraction_successes": 0, "extraction_failures": 0}
        self.config = {"base_url": "", "model": "", "api_key_present": False}

    async def process_dataframe(self, raw, output_path, links_path, as_of=None):
        self.metrics["extraction_failures"] += 1
        raise RuntimeError("MacroNewsLLMExtractor is unavailable; extraction disabled fail-closed")
