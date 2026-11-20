from datetime import datetime, timezone, timedelta
from models.user import db


class Feedback(db.Model):
    __tablename__ = 'feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # suggestion, bug, other
    content = db.Column(db.Text, nullable=False)
    contact = db.Column(db.String(100))  # Optional contact info
    image_url = db.Column(db.String(500)) # Optional screenshot
    status = db.Column(db.String(20), default='pending') # pending, processed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone(timedelta(hours=8))))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'content': self.content,
            'contact': self.contact,
            'image_url': self.image_url,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }
