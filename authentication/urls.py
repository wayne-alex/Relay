from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('', views.workspace, name='dashboard'),

    path('api/send/', views.send_request_api, name='send_request_api'),
    path('api/import-curl/', views.import_curl_api, name='import_curl_api'),
    path('api/extract-variable/', views.extract_variable_api, name='extract_variable_api'),
    path('api/collections/create/', views.create_collection_api, name='create_collection_api'),
    path('api/collections/<int:collection_id>/delete/', views.delete_collection_api, name='delete_collection_api'),

    path('api/requests/save/', views.save_request_api, name='save_request_api'),
    path('api/requests/<int:request_id>/load/', views.load_request_api, name='load_request_api'),
    path('api/requests/<int:request_id>/delete/', views.delete_request_api, name='delete_request_api'),

    path('api/history/', views.history_list_api, name='history_list_api'),
    path('api/history/<int:history_id>/load/', views.load_history_api, name='load_history_api'),
    path('api/history/<int:history_id>/save/', views.save_history_to_collection_api,
         name='save_history_to_collection_api'),

    path('api/environments/save/', views.save_environment_api, name='save_environment_api'),
    path('api/environments/', views.list_environments_api, name='list_environments_api'),

    path('api/requests/<int:request_id>/trend/', views.saved_request_trend_api, name='saved_request_trend_api'),
    path('api/collections/<int:collection_id>/export/', views.export_collection_api, name='export_collection_api'),
    path('api/collections/import/', views.import_collection_api, name='import_collection_api'),
    path('api/extract-html-variable/', views.extract_html_variable_api, name='extract_html_variable_api'),
    path('api/environments/<int:env_id>/', views.get_environment_api, name='get_environment_api'),
    path('api/environments/<int:env_id>/update/', views.update_environment_api, name='update_environment_api'),
    path('api/environments/<int:env_id>/delete/', views.delete_environment_api, name='delete_environment_api'),

    path('api/flows/create/', views.create_flow_api, name='create_flow_api'),
    path('api/flows/<int:flow_id>/delete/', views.delete_flow_api, name='delete_flow_api'),
    path('api/flows/<int:flow_id>/', views.flow_detail_api, name='flow_detail_api'),
    path('api/flows/<int:flow_id>/run/', views.run_flow_api, name='run_flow_api'),
    path('api/save_assertions/', views.save_assertions, name='save_assertions_api'),
    path('api/get_assertions/', views.get_assertions, name='get_assertions_api'),
    path('api/run_assertions/', views.run_assertions, name='run_assertions_api'),
    path('api/save_assertions/', views.save_assertions_api, name='save_assertions_api'),
    path('api/run_assertions/', views.run_assertions_api, name='run_assertions_api'),
    path('api/requests/update/', views.update_request_api, name='update_request_api'),
    path('api/refresh-collections/', views.refresh_collections_api, name='refresh_collections_api'),
path('api/flows/<int:flow_id>/update/', views.update_flow_api, name='update_flow_api'),

]
