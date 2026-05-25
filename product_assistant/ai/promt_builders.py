class PromptEngine:
    def __init__(self, role: str, template: str):
        self._role = role
        self._template = template

    def build(self, question: str, product_info: str) -> str:
        """
        Формирует промпт из роли, информации о продукте и вопроса пользователя.
        """
        try:
            return self._template.format(
                role=self._role,
                product_info=product_info,
                question=question,
            )
        except KeyError as e:
            raise ValueError(f"Ошибка в шаблоне промпта: отсутствует ключ {e}")
