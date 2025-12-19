from feast import Entity

# Entité principale : un utilisateur StreamFlow identifié par user_id
user = Entity(
    name="user",
    join_keys=["user_id"],
    description="Uti StreamFlow identifié de manière unique par user_id."
)