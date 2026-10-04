from django.urls import path

from . import views

app_name = 'news'

urlpatterns = [
    path('<int:pk>/', views.detail, name='detail'),
    path('category/<str:category>/', views.category, name='category'),
    path('search/', views.search, name='search'),  # added by shubham - news search
    path('create/', views.NewsCreateView.as_view(), name='create'),  # added by shubham - CRUD: create
    path('<int:pk>/edit/', views.NewsUpdateView.as_view(), name='edit'),  # added by shubham - CRUD: update
    path('<int:pk>/delete/', views.NewsDeleteView.as_view(), name='delete'),  # added by shubham - CRUD: delete
    path('my-posts/', views.my_posts, name='my_posts'),  # added by shubham - user's own posts
    path('refresh/', views.refresh, name='refresh'),  # added by shubham - staff: fetch GNews now
]
