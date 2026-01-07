"""
Collaboration Hub Models for Enterprise Customer Success Platform

Enables internal collaboration for Customer Success teams:
- Resource library (documents, templates, guides)
- Team notes and shared knowledge
- Activity tracking
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CSResource(Base):
    """
    Team resource library item (documents, templates, guides, etc.)
    """
    __tablename__ = "cs_resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text)

    # Resource type
    resource_type = Column(
        SQLEnum('document', 'video', 'template', 'checklist', 'guide', 'script', 'link', name='cs_resource_type_enum'),
        nullable=False
    )

    # Category
    category = Column(
        SQLEnum('onboarding', 'training', 'playbooks', 'processes', 'best_practices', 'templates', 'general', name='cs_resource_category_enum'),
        default='general'
    )

    # Content
    content = Column(Text)  # For text-based resources
    content_html = Column(Text)  # Rich text content
    url = Column(String(1000))  # For external links or file URLs
    file_path = Column(String(500))  # For uploaded files
    file_size = Column(Integer)  # In bytes
    file_type = Column(String(50))  # MIME type

    # Organization
    tags = Column(JSON)  # ["onboarding", "essential", "advanced"]
    is_featured = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)

    # Metrics
    views_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    downloads_count = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)
    is_archived = Column(Boolean, default=False)

    # Ownership and permissions
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    visibility = Column(
        SQLEnum('all', 'team', 'managers', 'admins', name='cs_visibility_enum'),
        default='all'
    )

    # Version tracking
    version = Column(String(20), default='1.0')
    parent_resource_id = Column(Integer, ForeignKey("cs_resources.id"))  # For versioning

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_viewed_at = Column(DateTime(timezone=True))

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_user_id], backref="created_resources")
    likes = relationship("CSResourceLike", back_populates="resource", cascade="all, delete-orphan")
    comments = relationship("CSResourceComment", back_populates="resource", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CSResource id={self.id} title='{self.title[:30]}...' type={self.resource_type}>"


class CSResourceLike(Base):
    """
    User like/favorite on a resource.
    """
    __tablename__ = "cs_resource_likes"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("cs_resources.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    resource = relationship("CSResource", back_populates="likes")
    user = relationship("User", backref="resource_likes")

    def __repr__(self):
        return f"<CSResourceLike resource_id={self.resource_id} user_id={self.user_id}>"


class CSResourceComment(Base):
    """
    Comment on a resource.
    """
    __tablename__ = "cs_resource_comments"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("cs_resources.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)

    content = Column(Text, nullable=False)
    parent_comment_id = Column(Integer, ForeignKey("cs_resource_comments.id"))  # For threaded comments

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    resource = relationship("CSResource", back_populates="comments")
    user = relationship("User", backref="resource_comments")
    replies = relationship("CSResourceComment", backref="parent_comment", remote_side=[id])

    def __repr__(self):
        return f"<CSResourceComment id={self.id} resource_id={self.resource_id}>"


class CSTeamNote(Base):
    """
    Team note for internal collaboration and knowledge sharing.
    """
    __tablename__ = "cs_team_notes"

    id = Column(Integer, primary_key=True, index=True)

    # Optional customer association
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)

    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    content_html = Column(Text)

    # Organization
    category = Column(String(100))  # User-defined category
    tags = Column(JSON)
    is_pinned = Column(Boolean, default=False)

    # Visibility
    visibility = Column(
        SQLEnum('all', 'team', 'managers', 'private', name='cs_note_visibility_enum'),
        default='team'
    )

    # Author
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="team_notes")
    created_by = relationship("User", foreign_keys=[created_by_user_id], backref="team_notes")
    comments = relationship("CSTeamNoteComment", back_populates="note", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CSTeamNote id={self.id} title='{self.title[:30]}...'>"


class CSTeamNoteComment(Base):
    """
    Comment on a team note.
    """
    __tablename__ = "cs_team_note_comments"

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("cs_team_notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)

    content = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    note = relationship("CSTeamNote", back_populates="comments")
    user = relationship("User", backref="team_note_comments")

    def __repr__(self):
        return f"<CSTeamNoteComment id={self.id} note_id={self.note_id}>"


class CSActivity(Base):
    """
    Activity feed for CS team collaboration.
    """
    __tablename__ = "cs_activities"

    id = Column(Integer, primary_key=True, index=True)

    # Activity type
    activity_type = Column(String(50), nullable=False)  # 'resource_created', 'note_posted', 'comment_added', etc.

    # What the activity relates to
    entity_type = Column(String(50))  # 'resource', 'note', 'customer', etc.
    entity_id = Column(Integer)

    # Activity details
    title = Column(String(300))
    description = Column(Text)
    metadata = Column(JSON)

    # Who performed the activity
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)

    # Optional customer association
    customer_id = Column(Integer, ForeignKey("customers.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="cs_activities")
    customer = relationship("Customer", backref="cs_activities")

    def __repr__(self):
        return f"<CSActivity id={self.id} type={self.activity_type}>"
