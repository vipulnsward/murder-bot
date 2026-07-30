class CreateAppUsers < ActiveRecord::Migration[7.2]
  def up
    create_table :app_users, if_not_exists: true
    add_column :app_users, :email, :text, null: false unless column_exists?(:app_users, :email)
    add_column :app_users, :password_digest, :text unless column_exists?(:app_users, :password_digest)
    add_column :app_users, :plan, :string, null: false, default: "free" unless column_exists?(:app_users, :plan)
    add_column :app_users, :stripe_customer_id, :string unless column_exists?(:app_users, :stripe_customer_id)
    add_column :app_users, :provider, :string unless column_exists?(:app_users, :provider)
    add_column :app_users, :provider_id, :string unless column_exists?(:app_users, :provider_id)
    add_column :app_users, :status, :string, null: false, default: "active" unless column_exists?(:app_users, :status)
    add_column :app_users, :current_period_end, :datetime unless column_exists?(:app_users, :current_period_end)
    add_column :app_users, :created_at, :datetime, null: false, default: -> { "CURRENT_TIMESTAMP" } unless column_exists?(:app_users, :created_at)
    add_column :app_users, :updated_at, :datetime, null: false, default: -> { "CURRENT_TIMESTAMP" } unless column_exists?(:app_users, :updated_at)
    change_column_null :app_users, :pw_hash, true if column_exists?(:app_users, :pw_hash)

    unless index_name_exists?(:app_users, "index_app_users_on_lower_email")
      add_index :app_users, "lower(email)", unique: true, name: "index_app_users_on_lower_email"
    end
    unless check_constraint_exists?(:app_users, name: "app_users_plan_check")
      add_check_constraint :app_users, "plan IN ('free', 'brain', 'auto', 'alliance')", name: "app_users_plan_check"
    end
    if table_exists?(:subscriptions)
      execute <<~SQL
        UPDATE app_users AS users
        SET plan = CASE WHEN subscriptions.plan IN ('free', 'brain', 'auto', 'alliance') THEN subscriptions.plan ELSE 'free' END,
            provider = subscriptions.provider,
            provider_id = subscriptions.provider_id,
            status = subscriptions.status,
            current_period_end = subscriptions.current_period_end
        FROM subscriptions
        WHERE subscriptions.user_id = users.id
      SQL
    end
  end

  def down
    raise ActiveRecord::IrreversibleMigration
  end
end
