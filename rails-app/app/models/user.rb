class User < ApplicationRecord
  self.table_name = "app_users"

  has_secure_password

  normalizes :email, with: ->(email) { email.strip.downcase }

  validates :email,
    presence: true,
    length: { maximum: 320 },
    format: { with: /\A[^@\s]+@[^@\s]+\.[^@\s]+\z/ },
    uniqueness: { case_sensitive: false }
  validates :password, length: { minimum: 8, maximum: 72 }, if: -> { password.present? }
  validates :plan, inclusion: { in: StripeBilling::PLANS.keys }
end
