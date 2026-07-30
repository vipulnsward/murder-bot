module Api
  class UsersController < ApplicationController
    before_action :authenticate_request

    def me
      render json: current_user.as_json(only: %i[id email plan stripe_customer_id provider provider_id status current_period_end])
    end
  end
end
