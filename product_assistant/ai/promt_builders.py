class PromptEngine:
    def __init__(self, role: str, template: str):
        self._role = role
        self._template = template

    def build(self, question: str, product_info: str, context: list[dict] | None = None) -> str:
        """
        Формирует промпт из:
        - роли
        - истории диалога
        - информации о продукте
        - вопроса пользователя
        """
        context_text = ""

        if context:
            context_text = "\n".join(
                f"{msg['role']}: {msg['content']}"
                for msg in context
            )

        try:
            return self._template.format(
                role=self._role,
                context=context_text,
                product_info=product_info,
                question=question,
            )
        except KeyError as e:
            raise ValueError(
                f"Ошибка в шаблоне промпта: отсутствует ключ {e}")