Rails.application.routes.draw do
  # Define your application routes per the DSL in https://guides.rubyonrails.org/routing.html

  # Reveal health status on /up that returns 200 if the app boots with no exceptions, otherwise 500.
  # Can be used by load balancers and uptime monitors to verify that the app is live.
  get "up" => "rails/health#show", as: :rails_health_check

  namespace :api do
    post :signup, to: "auth#signup"
    post :login, to: "auth#login"
    get :me, to: "users#me"
    get "counter-generals", to: "brain#counter_generals"
    get "dashboard/status", to: "dashboard#status"
    get "billing/plans", to: "billing#plans"
    post "billing/checkout", to: "billing#checkout"
    post "billing/stripe/webhook", to: "billing#stripe_webhook"
  end
end
