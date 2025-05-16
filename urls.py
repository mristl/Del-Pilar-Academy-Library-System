
from django.contrib import admin
from django.urls import path
from . import views
from django.contrib.auth.views import PasswordResetView

urlpatterns = [
    path('admin/', admin.site.urls),  
    path('register/', views.register, name='register'),
    path('login/', views.loginPage, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('confirm_email/', views.confirm_email, name='confirm_email'),
    path('reset_password/', views.reset_passwordPage, name = 'reset_password'),
    path('activate/<uidb64>/<token>', views.activate, name='activate'),
    path('reset/<uidb64>/<token>/',views.reset_password_done,name='reset_password_done'),
    path('circulation/', views.circulation, name='circulation'),

#backup
    path('backup/', views.backup_view, name='backup'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),

#anything past this is only when you're able to log in already.

    path('', views.view_books, name='home_page'),
    path('borrow_book/', views.borrow_book, name="borrow_book"),
    path('view_books/', views.view_books, name='view_books'),
    path('return_book/', views.return_book, name='return_book'),
    path('view_book_record/<str:control_number>/', views.view_book_record, name='view_book_record'),
    path('get-next-accession/', views.get_next_accession_ajax, name='get_next_accession_ajax'),


    path('computer-use/', views.computer_use, name='computer_use'),
    path('reports/', views.generate_report, name='reports'),
    path('reports/viewreport/', views.view_report, name='view_report'),
    path("download_report/", views.download_report, name="download_report"),
    path('confirm_return/<str:accession_number>/', views.confirm_return, name='confirm_return'),
    path('book_records/', views.book_records, name='book_records'),
    path('process_return/<str:accession_number>/', views.process_return, name='process_return'),

    path('add_books/', views.add_book, name='add_books'),
    path('admin-tools/overdue-simulator/', views.overdue_simulation_tool, name='overdue_simulation_tool'),
    
    path('all_library_users/', views.all_library_users, name='all_library_users'),
    path('update_user/', views.update_user, name='update_user'),
    path('flag_user/<str:id_number>/', views.flag_user, name='flag_user'),
    path('flag_user/<str:id_number>/check', views.check_borrowed_books, name='check_borrowed_books'),
    path('get_user_flag_status/<str:id_number>/',views. get_user_flag_status, name='get_user_flag_status'),
    path('computer-use/', views.computer_use, name='computer_use'),
    path('get_user_details/<str:user_id>/', views.get_user_details, name='get_user_details'),

    # Updated library user management paths
    path('add_library_users/', views.add_library_users, name='add_library_users'),
    path('new_school_year/', views.new_school_year, name='new_school_year'),
    path('upload_users_csv/', views.upload_users_csv, name='upload_users_csv'),
    path('manual_add_user/', views.manual_add_user, name='manual_add_user'),
]





