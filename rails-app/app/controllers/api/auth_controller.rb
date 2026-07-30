module Api
  class AuthController < ApplicationController
    def signup
      user = User.new(auth_params)

      if user.save
        render json: auth_response(user), status: :created
      else
        status = user.errors.of_kind?(:email, :taken) ? :conflict : :unprocessable_entity
        render json: { detail: user.errors.full_messages.to_sentence }, status:
      end
    rescue ActiveRecord::RecordNotUnique
      render json: { detail: "Email already registered" }, status: :conflict
    end

    def login
      user = User.find_by(email: params[:email].to_s.strip.downcase)

      if user&.authenticate(params[:password])
        render json: auth_response(user)
      else
        render json: { detail: "Invalid email or password" }, status: :unauthorized
      end
    end

    private

    def auth_params
      params.permit(:email, :password)
    end

    def auth_response(user)
      {
        token: issue_token(user),
        user: user.as_json(only: %i[id email plan stripe_customer_id provider provider_id status current_period_end])
      }
    end
  end
end
