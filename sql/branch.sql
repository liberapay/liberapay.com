UPDATE wallets
   SET is_current = true
  FROM participants p
 WHERE p.id = owner
   AND p.mangopay_user_id = remote_owner_id
   AND is_current IS NULL;
